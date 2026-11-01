"""Tests des espaces personnels : accès, cloisonnement des données, documents privés."""

import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Roles
from catalog.models import Categorie, DocumentFormation, Formation
from enrollments import services
from enrollments.models import Candidat, Inscription, Session
from trainers.models import Formateur

Utilisateur = get_user_model()
FICHIERS_TEST = tempfile.mkdtemp(prefix='media_test_')
AUJOURD_HUI = timezone.localdate()


def compte(email, role=None, **champs):
    utilisateur = Utilisateur.objects.create_user(username=email.split('@')[0], email=email, password='x', **champs)
    if role:
        utilisateur.groups.add(Group.objects.get(name=role))
    return utilisateur


@override_settings(FICHIERS_PRIVES_ROOT=FICHIERS_TEST, MEDIA_ROOT=FICHIERS_TEST)
class EspacesTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(FICHIERS_TEST, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        categorie = Categorie.objects.create(nom='Informatique')
        cls.python = Formation.objects.create(categorie=categorie, titre='Python', resume='r', duree_heures=20,
                                              prix=Decimal('500'), est_publiee=True)
        cls.excel = Formation.objects.create(categorie=categorie, titre='Excel', resume='r', duree_heures=10,
                                             prix=Decimal('300'), est_publiee=True)
        # Formateurs
        cls.compte_sami = compte('sami@exemple.tn', Roles.FORMATEUR)
        cls.sami = Formateur.objects.create(nom='Trabelsi', prenom='Sami', utilisateur=cls.compte_sami)
        cls.compte_nadia = compte('nadia@exemple.tn', Roles.FORMATEUR)
        cls.nadia = Formateur.objects.create(nom='Gharbi', prenom='Nadia', utilisateur=cls.compte_nadia)
        # Sessions
        cls.session_python = Session.objects.create(
            formation=cls.python, formateur=cls.sami, code='PY-1', statut=Session.Statut.OUVERTE, places_max=10,
            date_debut=AUJOURD_HUI + timedelta(days=10), date_fin=AUJOURD_HUI + timedelta(days=20), lieu='Salle A',
        )
        cls.session_excel = Session.objects.create(
            formation=cls.excel, formateur=cls.nadia, code='XL-1', statut=Session.Statut.OUVERTE, places_max=10,
            date_debut=AUJOURD_HUI + timedelta(days=5), date_fin=AUJOURD_HUI + timedelta(days=6),
        )
        # Candidats
        cls.compte_amira = compte('amira@exemple.tn', Roles.CANDIDAT)
        cls.amira = Candidat.objects.create(nom='Ben Salah', prenom='Amira', telephone='98123456', email='amira@exemple.tn',
                                            cin='01234567', utilisateur=cls.compte_amira)
        cls.compte_karim = compte('karim@exemple.tn', Roles.CANDIDAT)
        cls.karim = Candidat.objects.create(nom='Jaziri', prenom='Karim', telephone='22333444', email='karim@exemple.tn',
                                            cin='07654321', utilisateur=cls.compte_karim)
        cls.inscription_amira = services.confirmer(services.inscrire(cls.amira, cls.session_python, notes='Paiera en 2 fois'))
        cls.inscription_karim = services.inscrire(cls.karim, cls.session_excel)  # en attente


# --- Accès et redirections -------------------------------------------------------------------

class AccesTests(EspacesTestCase):
    def test_visiteur_redirige_vers_la_connexion(self):
        for nom in ('espaces:tableau', 'espaces:candidat', 'espaces:profil', 'espaces:formateur'):
            with self.subTest(nom=nom):
                reponse = self.client.get(reverse(nom))
                self.assertRedirects(reponse, f"{reverse('accounts:connexion')}?next={reverse(nom)}")

    def test_tableau_dirige_chacun_vers_son_espace(self):
        cas = [
            (self.compte_amira, reverse('espaces:candidat')),
            (self.compte_sami, reverse('espaces:formateur')),
            (compte('staff@exemple.tn', is_staff=True), reverse('admin:index')),
        ]
        for utilisateur, attendu in cas:
            with self.subTest(utilisateur=utilisateur.email):
                self.client.force_login(utilisateur)
                self.assertRedirects(self.client.get(reverse('espaces:tableau')), attendu, fetch_redirect_response=False)

    def test_compte_sans_fiche(self):
        self.client.force_login(compte('seul@exemple.tn', Roles.CANDIDAT))  # rôle mais aucune fiche
        self.assertContains(self.client.get(reverse('espaces:tableau')), 'Aucun espace disponible')
        self.assertEqual(self.client.get(reverse('espaces:candidat')).status_code, 403)

    def test_fiche_sans_le_role(self):
        sans_role = compte('sansrole@exemple.tn')
        Candidat.objects.create(nom='A', prenom='B', telephone='98000009', utilisateur=sans_role)
        self.client.force_login(sans_role)
        self.assertEqual(self.client.get(reverse('espaces:candidat')).status_code, 403)

    def test_cloisonnement_des_roles(self):
        self.client.force_login(self.compte_amira)
        self.assertEqual(self.client.get(reverse('espaces:formateur')).status_code, 403)
        self.client.force_login(self.compte_sami)
        self.assertEqual(self.client.get(reverse('espaces:candidat')).status_code, 403)

    def test_formateur_desactive_sans_acces(self):
        Formateur.objects.filter(pk=self.sami.pk).update(est_actif=False)
        self.client.force_login(self.compte_sami)
        self.assertEqual(self.client.get(reverse('espaces:formateur')).status_code, 403)

    def test_double_role_choix_de_l_espace(self):
        Candidat.objects.create(nom='Trabelsi', prenom='Sami', telephone='98000010', utilisateur=self.compte_sami)
        self.compte_sami.groups.add(Group.objects.get(name=Roles.CANDIDAT))
        self.client.force_login(self.compte_sami)
        self.assertContains(self.client.get(reverse('espaces:tableau')), 'Choisissez votre espace')


# --- Espace candidat -------------------------------------------------------------------------

class EspaceCandidatTests(EspacesTestCase):
    def test_voit_ses_inscriptions_et_pas_celles_des_autres(self):
        self.client.force_login(self.compte_amira)
        reponse = self.client.get(reverse('espaces:candidat'))
        self.assertContains(reponse, 'Python')
        self.assertContains(reponse, 'PY-1')
        self.assertContains(reponse, 'Confirmée')
        self.assertContains(reponse, '500 DT')
        self.assertNotContains(reponse, 'XL-1')
        self.assertNotContains(reponse, 'Karim')

    def test_notes_internes_jamais_affichees(self):
        self.client.force_login(self.compte_amira)
        self.assertNotContains(self.client.get(reverse('espaces:candidat')), 'Paiera en 2 fois')

    def test_aucun_id_numerique(self):
        self.client.force_login(self.compte_amira)
        contenu = self.client.get(reverse('espaces:candidat')).content.decode()
        self.assertNotIn(f'/{self.inscription_amira.pk}/', contenu)
        self.assertNotIn(f'/{self.session_python.pk}/', contenu)


class ProfilCandidatTests(EspacesTestCase):
    def setUp(self):
        self.client.force_login(self.compte_amira)

    def test_modifie_telephone_et_email_y_compris_l_email_de_connexion(self):
        reponse = self.client.post(reverse('espaces:profil'), {'telephone': '+216 55 666 777', 'email': 'Amira.Nouvelle@exemple.tn'}, follow=True)
        self.assertRedirects(reponse, reverse('espaces:candidat'))
        self.assertContains(reponse, 'Vos coordonnées ont été mises à jour.')
        self.amira.refresh_from_db()
        self.compte_amira.refresh_from_db()
        self.assertEqual(self.amira.telephone, '55666777')
        self.assertEqual(self.amira.email, 'amira.nouvelle@exemple.tn')
        self.assertEqual(self.compte_amira.email, 'amira.nouvelle@exemple.tn')

    def test_nom_et_cin_non_modifiables(self):
        self.client.post(reverse('espaces:profil'), {
            'telephone': '98123456', 'email': 'amira@exemple.tn', 'nom': 'Pirate', 'cin': '99999999',
        })
        self.amira.refresh_from_db()
        self.assertEqual(self.amira.nom, 'Ben Salah')
        self.assertEqual(self.amira.cin, '01234567')

    def test_email_d_un_autre_compte_refuse(self):
        reponse = self.client.post(reverse('espaces:profil'), {'telephone': '98123456', 'email': 'KARIM@exemple.tn'})
        self.assertContains(reponse, 'déjà utilisée par un autre compte')
        self.compte_amira.refresh_from_db()
        self.assertEqual(self.compte_amira.email, 'amira@exemple.tn')

    def test_email_obligatoire_et_telephone_valide(self):
        reponse = self.client.post(reverse('espaces:profil'), {'telephone': '12', 'email': ''})
        self.assertIn('telephone', reponse.context['form'].errors)
        self.assertIn('email', reponse.context['form'].errors)


# --- Espace formateur ------------------------------------------------------------------------

class EspaceFormateurTests(EspacesTestCase):
    def setUp(self):
        self.client.force_login(self.compte_sami)

    def test_voit_seulement_ses_sessions(self):
        reponse = self.client.get(reverse('espaces:formateur'))
        self.assertContains(reponse, 'PY-1')
        self.assertNotContains(reponse, 'XL-1')
        self.assertIn(self.session_python, reponse.context['a_venir'])

    def test_classement_en_cours_et_passees(self):
        en_cours = Session.objects.create(formation=self.python, formateur=self.sami, code='PY-EN-COURS', places_max=5,
                                          statut=Session.Statut.EN_COURS, date_debut=AUJOURD_HUI - timedelta(days=1),
                                          date_fin=AUJOURD_HUI + timedelta(days=1))
        passee = Session.objects.create(formation=self.python, formateur=self.sami, code='PY-PASSEE', places_max=5,
                                        statut=Session.Statut.TERMINEE, date_debut=AUJOURD_HUI - timedelta(days=30),
                                        date_fin=AUJOURD_HUI - timedelta(days=20))
        contexte = self.client.get(reverse('espaces:formateur')).context
        self.assertEqual(contexte['en_cours'], [en_cours])
        self.assertEqual(contexte['passees'], [passee])

    def test_detail_inscrits_confirmes_avec_coordonnees_sans_donnees_sensibles(self):
        services.inscrire(self.karim, self.session_python)  # en attente : n'apparaît pas
        reponse = self.client.get(reverse('espaces:session', kwargs={'uuid': self.session_python.uuid}))
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual([i.candidat for i in reponse.context['inscrits']], [self.amira])
        for visible in ('Ben Salah', 'Amira', '98123456', 'amira@exemple.tn'):
            self.assertContains(reponse, visible)
        for cache in ('01234567', '500 DT', 'Paiera en 2 fois', 'Karim'):
            self.assertNotContains(reponse, cache)

    def test_session_d_un_collegue_introuvable(self):
        reponse = self.client.get(reverse('espaces:session', kwargs={'uuid': self.session_excel.uuid}))
        self.assertEqual(reponse.status_code, 404)

    def test_adresse_par_id_numerique_impossible(self):
        self.assertEqual(self.client.get(f'/espace/formateur/sessions/{self.session_python.pk}/').status_code, 404)


# --- Documents privés ------------------------------------------------------------------------

class DocumentsPrivesTests(EspacesTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.support_python = DocumentFormation.objects.create(
            formation=cls.python, titre='Support de cours', est_public=False,
            fichier=SimpleUploadedFile('support.pdf', b'%PDF-1.4 support python'),
        )
        cls.brochure = DocumentFormation.objects.create(
            formation=cls.python, titre='Brochure', est_public=True, fichier=SimpleUploadedFile('brochure.pdf', b'%PDF brochure'),
        )
        cls.support_excel = DocumentFormation.objects.create(
            formation=cls.excel, titre='Exercices Excel', est_public=False, fichier=SimpleUploadedFile('ex.pdf', b'%PDF excel'),
        )

    def telecharger(self, document):
        reponse = self.client.get(document.fichier.url)
        # Ferme le fichier servi : sous Windows, un fichier resté ouvert ne peut pas être supprimé au nettoyage.
        # (On ferme le fichier lui-même : reponse.close() émettrait le signal de fin de requête, qui fermerait
        # la connexion à la base au milieu de la transaction du test.)
        fichier = getattr(reponse, 'file_to_stream', None)
        if fichier is not None:
            self.addCleanup(fichier.close)
        return reponse

    def test_stockage_hors_du_dossier_media_et_url_protegee(self):
        self.assertTrue(self.support_python.fichier.url.startswith('/espace/fichiers/formations/documents/'))
        self.assertTrue(self.support_python.fichier.path.startswith(FICHIERS_TEST))

    def test_candidat_confirme_telecharge(self):
        self.client.force_login(self.compte_amira)
        reponse = self.telecharger(self.support_python)
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(b''.join(reponse.streaming_content), b'%PDF-1.4 support python')
        self.assertIn('support-de-cours.pdf', reponse['Content-Disposition'])
        self.assertEqual(reponse['Cache-Control'], 'private, no-store')
        self.assertContains(self.client.get(reverse('espaces:candidat')), 'Support de cours')

    def test_candidat_en_attente_ou_autre_formation_refuse(self):
        self.client.force_login(self.compte_karim)  # en attente sur Excel, rien sur Python
        self.assertEqual(self.telecharger(self.support_excel).status_code, 404)
        self.assertEqual(self.telecharger(self.support_python).status_code, 404)
        self.assertNotContains(self.client.get(reverse('espaces:candidat')), 'Exercices Excel')

    def test_formateur_de_la_formation_seulement(self):
        self.client.force_login(self.compte_sami)
        self.assertEqual(self.telecharger(self.support_python).status_code, 200)
        self.assertEqual(self.telecharger(self.support_excel).status_code, 404)

    def test_document_public_pour_tous_et_prive_jamais_pour_un_visiteur(self):
        self.assertEqual(self.telecharger(self.brochure).status_code, 200)
        self.assertEqual(self.telecharger(self.support_python).status_code, 404)
        self.assertContains(self.client.get(self.python.get_absolute_url()), self.brochure.fichier.url)

    def test_document_public_d_une_formation_non_publiee(self):
        Formation.objects.filter(pk=self.python.pk).update(est_publiee=False)
        self.assertEqual(self.telecharger(self.brochure).status_code, 404)

    def test_personnel_avec_droit(self):
        gestionnaire = compte('gest@exemple.tn', Roles.GESTIONNAIRE, is_staff=True)
        self.client.force_login(gestionnaire)
        self.assertEqual(self.telecharger(self.support_excel).status_code, 200)

    def test_chemins_inventes_refuses(self):
        self.client.force_login(compte('gest2@exemple.tn', Roles.GESTIONNAIRE, is_staff=True))
        for chemin in ('../../config/settings.py', 'formations/documents/inexistant.pdf', '..%2F..%2F.env'):
            with self.subTest(chemin=chemin):
                self.assertEqual(self.client.get(f'/espace/fichiers/{chemin}').status_code, 404)

    def test_annulation_retire_l_acces(self):
        services.annuler(Inscription.objects.get(pk=self.inscription_amira.pk))
        self.client.force_login(self.compte_amira)
        self.assertEqual(self.telecharger(self.support_python).status_code, 404)
