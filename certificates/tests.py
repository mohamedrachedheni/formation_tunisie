import shutil
import tempfile
from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import Roles
from catalog.models import Categorie, Formation
from core.models import ParametresCentre
from enrollments.models import Candidat, Inscription, Session

from . import services
from .models import Certificat
from .pdf import generer_pdf
from .services import CertificatImpossible

Utilisateur = get_user_model()


def image_png(couleur=(0, 32, 91, 255)):
    tampon = BytesIO()
    Image.new('RGBA', (300, 120), couleur).save(tampon, 'PNG')
    return SimpleUploadedFile('image.png', tampon.getvalue(), content_type='image/png')


class DonneesMixin:
    @classmethod
    def setUpTestData(cls):
        categorie = Categorie.objects.create(nom='Électricité')
        cls.formation = Formation.objects.create(
            categorie=categorie, titre='Électricité bâtiment', resume='r', duree_heures=120, prix=Decimal('900.000'),
        )
        cls.session = Session.objects.create(
            formation=cls.formation, date_debut=date(2026, 9, 1), date_fin=date(2026, 10, 15),
            places_max=10, statut=Session.Statut.TERMINEE,
        )
        cls.candidat = Candidat.objects.create(
            prenom='Amira', nom='Ben Salah', telephone='98123456', email='amira@exemple.tn', cin='01234567',
        )
        cls.autre_candidat = Candidat.objects.create(prenom='Karim', nom='Jaziri', telephone='22333444')
        ParametresCentre.objects.create(
            nom='Centre Test', ville='Sousse', signataire_nom='Ridha Baraket', signataire_fonction='Directeur',
        )

    def inscription(self, candidat=None, resultat=Inscription.Resultat.REUSSI, statut=Inscription.Statut.TERMINEE):
        return Inscription.objects.create(
            candidat=candidat or self.candidat, session=self.session, statut=statut,
            resultat=resultat if statut == Inscription.Statut.TERMINEE else '',
            prix_convenu=Decimal('900.000'), date_confirmation=timezone.now(),
        )

    def utilisateur(self, role, nom='gest', **champs):
        utilisateur = Utilisateur.objects.create_user(
            username=nom, email=f'{nom}@exemple.tn', password='MotDePasse!2026', **champs,
        )
        utilisateur.groups.add(Group.objects.get(name=role))
        return utilisateur


# --- Règles métier --------------------------------------------------------------------------

class DelivranceTests(DonneesMixin, TestCase):
    def setUp(self):
        self.gestionnaire = self.utilisateur(Roles.GESTIONNAIRE, is_staff=True)

    def test_reussi_donne_un_certificat_de_reussite_avec_contenu_recopie(self):
        certificat, est_nouveau = services.delivrer(self.inscription(), self.gestionnaire)
        self.assertTrue(est_nouveau)
        self.assertEqual(certificat.type, Certificat.Type.REUSSITE)
        self.assertEqual(certificat.numero, f'CERT-{timezone.localdate().year}-00001')
        self.assertEqual(certificat.statut, Certificat.Statut.VALIDE)
        self.assertEqual(certificat.titulaire, 'Amira Ben Salah')
        self.assertEqual(certificat.formation_titre, 'Électricité bâtiment')
        self.assertEqual(certificat.duree_heures, 120)
        self.assertEqual((certificat.date_debut, certificat.date_fin), (date(2026, 9, 1), date(2026, 10, 15)))
        self.assertEqual((certificat.signataire_nom, certificat.signataire_fonction), ('Ridha Baraket', 'Directeur'))
        self.assertEqual(certificat.delivre_par, self.gestionnaire)
        self.assertEqual(certificat.date_delivrance, timezone.localdate())

    def test_echoue_donne_une_attestation_de_participation(self):
        certificat, _ = services.delivrer(self.inscription(resultat=Inscription.Resultat.ECHOUE), self.gestionnaire)
        self.assertEqual(certificat.type, Certificat.Type.PARTICIPATION)

    def test_inscription_non_terminee_refusee(self):
        for statut in (Inscription.Statut.EN_ATTENTE, Inscription.Statut.CONFIRMEE, Inscription.Statut.ANNULEE):
            with self.subTest(statut=statut):
                Inscription.objects.all().delete()
                with self.assertRaises(CertificatImpossible):
                    services.delivrer(self.inscription(statut=statut), self.gestionnaire)
        self.assertFalse(Certificat.objects.exists())

    def test_un_seul_document_par_inscription(self):
        inscription = self.inscription()
        services.delivrer(inscription, self.gestionnaire)
        with self.assertRaisesMessage(CertificatImpossible, 'déjà été délivré'):
            services.delivrer(inscription, self.gestionnaire)
        self.assertEqual(Certificat.objects.count(), 1)

    def test_numeros_sequentiels_et_remis_a_zero_chaque_annee(self):
        annee = timezone.localdate().year
        premier, _ = services.delivrer(self.inscription(), self.gestionnaire)
        second, _ = services.delivrer(self.inscription(candidat=self.autre_candidat), self.gestionnaire)
        self.assertEqual((premier.numero, second.numero), (f'CERT-{annee}-00001', f'CERT-{annee}-00002'))
        troisieme_candidat = Candidat.objects.create(prenom='Sana', nom='Toumi', telephone='55666777')
        with mock.patch('certificates.services.timezone.localdate', return_value=date(annee + 1, 1, 5)):
            suivant, _ = services.delivrer(self.inscription(candidat=troisieme_candidat), self.gestionnaire)
        self.assertEqual(suivant.numero, f'CERT-{annee + 1}-00001')

    def test_contenu_fige_apres_delivrance(self):
        certificat, _ = services.delivrer(self.inscription(), self.gestionnaire)
        Formation.objects.filter(pk=self.formation.pk).update(titre='Nouveau titre')
        Candidat.objects.filter(pk=self.candidat.pk).update(nom='Autre')
        ParametresCentre.objects.update(signataire_nom='Nouveau directeur')
        certificat.refresh_from_db()
        self.assertEqual(certificat.formation_titre, 'Électricité bâtiment')
        self.assertEqual(certificat.titulaire, 'Amira Ben Salah')
        self.assertEqual(certificat.signataire_nom, 'Ridha Baraket')

    def test_mise_a_jour_corrige_le_contenu_sans_changer_numero_ni_date(self):
        certificat, _ = services.delivrer(self.inscription(), self.gestionnaire)
        Candidat.objects.filter(pk=self.candidat.pk).update(nom='Ben Salah Trabelsi')
        Certificat.objects.filter(pk=certificat.pk).update(date_delivrance=date(2026, 10, 20))
        corrige = services.mettre_a_jour(certificat)
        self.assertEqual(corrige.titulaire, 'Amira Ben Salah Trabelsi')
        self.assertEqual(corrige.numero, certificat.numero)
        self.assertEqual(corrige.date_delivrance, date(2026, 10, 20))

    def test_annulation_avec_motif_obligatoire(self):
        certificat, _ = services.delivrer(self.inscription(), self.gestionnaire)
        for motif in ('', '   '):
            with self.assertRaisesMessage(CertificatImpossible, 'motif'):
                services.annuler(certificat, motif)
        annule = services.annuler(certificat, 'Erreur sur le nom')
        self.assertEqual(annule.statut, Certificat.Statut.ANNULE)
        self.assertIsNotNone(annule.date_annulation)
        with self.assertRaisesMessage(CertificatImpossible, 'déjà annulé'):
            services.annuler(annule, 'Encore')
        with self.assertRaises(CertificatImpossible):
            services.mettre_a_jour(annule)

    def test_nouvelle_delivrance_apres_annulation_garde_le_numero(self):
        inscription = self.inscription()
        certificat, _ = services.delivrer(inscription, self.gestionnaire)
        services.annuler(certificat, 'Erreur')
        remis, est_nouveau = services.delivrer(inscription, self.gestionnaire)
        self.assertFalse(est_nouveau)
        self.assertEqual(remis.pk, certificat.pk)
        self.assertEqual(remis.numero, certificat.numero)
        self.assertEqual(remis.statut, Certificat.Statut.VALIDE)
        self.assertEqual((remis.motif_annulation, remis.date_annulation), ('', None))
        self.assertEqual(Certificat.objects.count(), 1)

    def test_contraintes_en_base(self):
        certificat, _ = services.delivrer(self.inscription(), self.gestionnaire)
        # Annulé sans motif : refusé par la base elle-même.
        with self.assertRaises(IntegrityError), transaction.atomic():
            Certificat.objects.filter(pk=certificat.pk).update(statut=Certificat.Statut.ANNULE)
        # Une inscription certifiée ne peut pas être supprimée.
        with self.assertRaises(ProtectedError):
            certificat.inscription.delete()


# --- PDF ------------------------------------------------------------------------------------

class PdfTests(DonneesMixin, TestCase):
    @classmethod
    def setUpClass(cls):
        # Dossier temporaire créé seulement si ces tests s'exécutent, et toujours supprimé ensuite :
        # les images de test ne vont jamais dans media/ ni dans fichiers_prives/.
        dossier = tempfile.mkdtemp(prefix='media_test_certificats_')
        cls.addClassCleanup(shutil.rmtree, dossier, ignore_errors=True)
        cls.enterClassContext(override_settings(MEDIA_ROOT=dossier, FICHIERS_PRIVES_ROOT=dossier))
        super().setUpClass()

    def setUp(self):
        self.certificat, _ = services.delivrer(self.inscription(), None)

    def test_pdf_produit_avec_logo_et_signature(self):
        parametres = ParametresCentre.obtenir()
        parametres.logo = image_png()
        parametres.signature = image_png((0, 0, 0, 0))
        parametres.save()
        # La signature est rangée dans le stockage privé, pas dans les médias publics.
        self.assertTrue(parametres.signature.name.endswith('.webp'))
        self.assertTrue(parametres.signature.url.startswith('/espace/fichiers/'))
        contenu = generer_pdf(self.certificat, 'https://exemple.tn/certificats/verifier/x/')
        self.assertTrue(contenu.startswith(b'%PDF'))
        self.assertIn(self.certificat.numero.encode(), contenu)

    def test_pdf_sans_parametres_ni_images_et_certificat_annule(self):
        ParametresCentre.objects.all().delete()
        services.annuler(self.certificat, 'Erreur')
        self.certificat.refresh_from_db()
        self.assertTrue(generer_pdf(self.certificat, 'https://exemple.tn/v/').startswith(b'%PDF'))

    def test_image_manquante_sur_le_disque_ne_bloque_pas_le_pdf(self):
        parametres = ParametresCentre.obtenir()
        ParametresCentre.objects.update(signature='signatures/absente.webp')
        parametres.refresh_from_db()
        with self.assertLogs('certificates.pdf', 'WARNING'):
            self.assertTrue(generer_pdf(self.certificat, 'https://exemple.tn/v/').startswith(b'%PDF'))

    def test_titre_avec_caracteres_speciaux_echappe(self):
        Certificat.objects.filter(pk=self.certificat.pk).update(formation_titre='Réseaux <b> & « Wi-Fi »')
        self.certificat.refresh_from_db()
        self.assertTrue(generer_pdf(self.certificat, 'https://exemple.tn/v/').startswith(b'%PDF'))


# --- Vérification publique ------------------------------------------------------------------

class VerificationPubliqueTests(DonneesMixin, TestCase):
    def setUp(self):
        self.certificat, _ = services.delivrer(self.inscription(), None)

    def test_certificat_valide_donnees_minimales(self):
        reponse = self.client.get(reverse('certificates:verifier', args=[self.certificat.uuid]))
        self.assertEqual(reponse.status_code, 200)
        for texte in ('Document authentique et valide', self.certificat.numero, 'Amira Ben Salah',
                      'Électricité bâtiment', 'Certificat de réussite', '01/09/2026', '15/10/2026'):
            self.assertContains(reponse, texte)
        # Jamais de données personnelles ou commerciales.
        for texte in ('01234567', '98123456', 'amira@exemple.tn', '900'):
            self.assertNotContains(reponse, texte)
        self.assertContains(reponse, '<meta name="robots" content="noindex, nofollow">', html=True)
        self.assertIn('no-store', reponse['Cache-Control'])

    def test_certificat_annule_sans_le_motif(self):
        services.annuler(self.certificat, 'Fraude constatée sur les présences')
        reponse = self.client.get(reverse('certificates:verifier', args=[self.certificat.uuid]))
        self.assertContains(reponse, 'Document annulé')
        self.assertNotContains(reponse, 'authentique et valide')
        self.assertNotContains(reponse, 'Fraude')

    def test_uuid_inconnu_ou_id_numerique_404(self):
        import uuid
        self.assertEqual(self.client.get(reverse('certificates:verifier', args=[uuid.uuid4()])).status_code, 404)
        self.assertEqual(self.client.get(f'/certificats/verifier/{self.certificat.pk}/').status_code, 404)
        self.assertEqual(self.client.get(f'/certificats/verifier/{self.certificat.numero}/').status_code, 404)


# --- Espace candidat ------------------------------------------------------------------------

class EspaceCandidatCertificatsTests(DonneesMixin, TestCase):
    def setUp(self):
        self.compte = self.utilisateur(Roles.CANDIDAT, nom='amira')
        Candidat.objects.filter(pk=self.candidat.pk).update(utilisateur=self.compte)
        self.certificat, _ = services.delivrer(self.inscription(), None)
        self.certificat_autre, _ = services.delivrer(self.inscription(candidat=self.autre_candidat), None)
        self.client.force_login(self.compte)

    def url_pdf(self, certificat):
        return reverse('espaces:certificat_pdf', args=[certificat.uuid])

    def test_liste_et_telechargement_de_ses_certificats(self):
        page = self.client.get(reverse('espaces:candidat'))
        self.assertContains(page, self.certificat.numero)
        self.assertContains(page, self.url_pdf(self.certificat))
        self.assertNotContains(page, self.certificat_autre.numero)
        reponse = self.client.get(self.url_pdf(self.certificat))
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse['Content-Type'], 'application/pdf')
        self.assertIn(f'{self.certificat.numero}.pdf', reponse['Content-Disposition'])
        self.assertIn('no-store', reponse['Cache-Control'])

    def test_certificat_d_un_autre_candidat_404(self):
        self.assertEqual(self.client.get(self.url_pdf(self.certificat_autre)).status_code, 404)

    def test_certificat_annule_ni_liste_ni_telechargeable(self):
        services.annuler(self.certificat, 'Erreur')
        self.assertNotContains(self.client.get(reverse('espaces:candidat')), self.certificat.numero)
        self.assertEqual(self.client.get(self.url_pdf(self.certificat)).status_code, 404)

    def test_visiteur_non_connecte_renvoye_a_la_connexion(self):
        self.client.logout()
        reponse = self.client.get(self.url_pdf(self.certificat))
        self.assertEqual(reponse.status_code, 302)
        self.assertIn(reverse('accounts:connexion'), reponse.url)


# --- Administration et droits ---------------------------------------------------------------

class AdministrationCertificatsTests(DonneesMixin, TestCase):
    def setUp(self):
        self.gestionnaire = self.utilisateur(Roles.GESTIONNAIRE, is_staff=True)
        self.administrateur = self.utilisateur(Roles.ADMINISTRATEUR, nom='admin', is_staff=True)
        self.client.force_login(self.gestionnaire)

    def test_droits_des_groupes(self):
        def droits(role):
            return set(Group.objects.get(name=role).permissions.filter(content_type__app_label='certificates')
                       .values_list('codename', flat=True))
        self.assertEqual(droits(Roles.ADMINISTRATEUR), {'view_certificat', 'delivrer_certificat', 'annuler_certificat'})
        self.assertEqual(droits(Roles.GESTIONNAIRE), {'view_certificat', 'delivrer_certificat'})
        self.assertEqual(droits(Roles.FORMATEUR), set())
        self.assertEqual(droits(Roles.CANDIDAT), set())

    def test_action_delivrer_depuis_les_inscriptions(self):
        inscription = self.inscription()
        page = self.client.get(reverse('admin:enrollments_inscription_changelist'))
        self.assertContains(page, 'delivrer_certificat')
        # Les actions d'origine restent disponibles.
        self.assertContains(page, 'terminer_reussi')
        reponse = self.client.post(reverse('admin:enrollments_inscription_changelist'), {
            'action': 'delivrer_certificat', '_selected_action': [inscription.pk],
        }, follow=True)
        certificat = Certificat.objects.get()
        self.assertEqual(certificat.delivre_par, self.gestionnaire)
        self.assertContains(reponse, certificat.numero)

    def test_action_delivrer_absente_sans_le_droit(self):
        self.inscription()
        sans_droit = Utilisateur.objects.create_user(username='lecteur', email='l@exemple.tn', is_staff=True)
        from django.contrib.auth.models import Permission
        sans_droit.user_permissions.add(Permission.objects.get(codename='view_inscription'))
        self.client.force_login(sans_droit)
        page = self.client.get(reverse('admin:enrollments_inscription_changelist'))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'delivrer_certificat')

    def test_annulation_reservee_a_l_administrateur_avec_motif(self):
        certificat, _ = services.delivrer(self.inscription(), self.gestionnaire)
        url = reverse('admin:certificates_certificat_changelist')
        self.assertNotContains(self.client.get(url), 'value="annuler"')

        self.client.force_login(self.administrateur)
        self.assertContains(self.client.get(url), 'value="annuler"')
        donnees = {'action': 'annuler', '_selected_action': [certificat.pk]}
        # 1) Page intermédiaire ; 2) confirmation sans motif refusée ; 3) confirmation avec motif.
        self.assertContains(self.client.post(url, donnees), 'Motif de l’annulation')
        self.client.post(url, {**donnees, 'confirmer': '1', 'motif': '  '})
        certificat.refresh_from_db()
        self.assertTrue(certificat.est_valide)
        self.client.post(url, {**donnees, 'confirmer': '1', 'motif': 'Erreur sur le nom'})
        certificat.refresh_from_db()
        self.assertEqual(certificat.statut, Certificat.Statut.ANNULE)
        self.assertEqual(certificat.motif_annulation, 'Erreur sur le nom')

    def test_ni_ajout_ni_modification_ni_suppression_meme_superutilisateur(self):
        certificat, _ = services.delivrer(self.inscription(), self.gestionnaire)
        superutilisateur = Utilisateur.objects.create_superuser(username='su', email='su@exemple.tn', password='x')
        self.client.force_login(superutilisateur)
        self.assertEqual(self.client.get(reverse('admin:certificates_certificat_add')).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:certificates_certificat_delete', args=[certificat.pk])).status_code, 403)
        url_fiche = reverse('admin:certificates_certificat_change', args=[certificat.pk])
        # Fiche en consultation seule : aucun bouton d'enregistrement.
        self.assertNotContains(self.client.get(url_fiche), 'name="_save"')
        self.client.post(url_fiche, {'titulaire': 'Pirate'})
        certificat.refresh_from_db()
        self.assertEqual(certificat.titulaire, 'Amira Ben Salah')

    def test_pdf_depuis_l_administration(self):
        certificat, _ = services.delivrer(self.inscription(), self.gestionnaire)
        url = reverse('admin:certificates_certificat_pdf', args=[certificat.pk])
        self.assertContains(self.client.get(reverse('admin:certificates_certificat_change', args=[certificat.pk])), url)
        reponse = self.client.get(url)
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse['Content-Type'], 'application/pdf')
        # Personnel sans droit sur les certificats : refusé.
        sans_droit = Utilisateur.objects.create_user(username='autre', email='a@exemple.tn', is_staff=True)
        self.client.force_login(sans_droit)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_mise_a_jour_depuis_l_administration(self):
        certificat, _ = services.delivrer(self.inscription(), self.gestionnaire)
        Candidat.objects.filter(pk=self.candidat.pk).update(prenom='Amirah')
        self.client.post(reverse('admin:certificates_certificat_changelist'), {
            'action': 'mettre_a_jour', '_selected_action': [certificat.pk],
        })
        certificat.refresh_from_db()
        self.assertEqual(certificat.titulaire, 'Amirah Ben Salah')


class DateFrancaiseTests(TestCase):
    def test_premier_du_mois(self):
        from .pdf import _date
        self.assertEqual(_date(date(2026, 9, 1)), '1er septembre 2026')
        self.assertEqual(_date(date(2026, 10, 15)), '15 octobre 2026')
