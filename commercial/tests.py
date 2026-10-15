from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Roles
from catalog.models import Categorie, Formation
from core.models import ParametresCentre

from .forms import DemandeContactForm
from .models import DemandeContact
from .views import MESSAGE_SUCCES

URL_CONTACT = reverse('commercial:contact')


def donnees_valides(**champs):
    donnees = {'nom': 'Amira Ben Salah', 'email': 'amira@exemple.tn', 'telephone': '98 123 456',
               'message': 'Je souhaite m’inscrire.', 'formation': '', 'site_web': ''}
    donnees.update(champs)
    return donnees


class AvecFormationsMixin:
    @classmethod
    def setUpTestData(cls):
        categorie = Categorie.objects.create(nom='Informatique')
        valeurs = {'resume': 'r', 'duree_heures': 20, 'prix': Decimal('300.000')}
        cls.publiee = Formation.objects.create(categorie=categorie, titre='Python', est_publiee=True, **valeurs)
        cls.brouillon = Formation.objects.create(categorie=categorie, titre='Brouillon', est_publiee=False, **valeurs)


# --- Modèle ---------------------------------------------------------------------------------

class DemandeContactModeleTests(TestCase):
    def test_valeurs_par_defaut_et_uuid(self):
        demande = DemandeContact.objects.create(nom='A', email='a@exemple.tn', message='m')
        self.assertEqual(demande.statut, DemandeContact.Statut.NOUVELLE)
        self.assertEqual(demande.source, DemandeContact.Source.FORMULAIRE)
        self.assertIsNotNone(demande.uuid)

    def test_base_refuse_une_demande_sans_email_ni_telephone(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            DemandeContact.objects.create(nom='A', message='m')

    def test_email_seul_ou_telephone_seul_acceptes(self):
        DemandeContact.objects.create(nom='A', email='a@exemple.tn', message='m')
        DemandeContact.objects.create(nom='B', telephone='71000000', message='m')
        self.assertEqual(DemandeContact.objects.count(), 2)

    def test_demande_conservee_si_la_formation_est_supprimee(self):
        categorie = Categorie.objects.create(nom='Langues')
        formation = Formation.objects.create(categorie=categorie, titre='Anglais', resume='r', duree_heures=10, prix=0)
        demande = DemandeContact.objects.create(nom='A', email='a@exemple.tn', message='m', formation=formation)
        formation.delete()
        demande.refresh_from_db()
        self.assertIsNone(demande.formation)


# --- Formulaire -----------------------------------------------------------------------------

class DemandeContactFormTests(AvecFormationsMixin, TestCase):
    def test_formulaire_valide(self):
        self.assertTrue(DemandeContactForm(donnees_valides()).is_valid())

    def test_email_ou_telephone_suffit(self):
        self.assertTrue(DemandeContactForm(donnees_valides(telephone='')).is_valid())
        self.assertTrue(DemandeContactForm(donnees_valides(email='')).is_valid())

    def test_sans_email_ni_telephone_refuse(self):
        formulaire = DemandeContactForm(donnees_valides(email='', telephone=''))
        self.assertFalse(formulaire.is_valid())
        self.assertIn('au moins un email ou un numéro', formulaire.non_field_errors()[0])

    def test_formats_de_telephone(self):
        for numero in ('71 123 456', '98-123-456', '+216 98 123 456', '98123456'):
            with self.subTest(numero=numero):
                self.assertTrue(DemandeContactForm(donnees_valides(telephone=numero)).is_valid())
        for numero in ('123', 'abcdefgh', '98 123 45a', '+'):
            with self.subTest(numero=numero):
                self.assertIn('telephone', DemandeContactForm(donnees_valides(telephone=numero)).errors)

    def test_champs_obligatoires(self):
        formulaire = DemandeContactForm(donnees_valides(nom='', message=''))
        self.assertIn('nom', formulaire.errors)
        self.assertIn('message', formulaire.errors)

    def test_formation_choisie_par_uuid(self):
        formulaire = DemandeContactForm(donnees_valides(formation=str(self.publiee.uuid)))
        self.assertTrue(formulaire.is_valid())
        self.assertEqual(formulaire.cleaned_data['formation'], self.publiee)

    def test_formation_par_id_numerique_refusee(self):
        self.assertIn('formation', DemandeContactForm(donnees_valides(formation=str(self.publiee.pk))).errors)

    def test_formation_non_publiee_refusee(self):
        self.assertIn('formation', DemandeContactForm(donnees_valides(formation=str(self.brouillon.uuid))).errors)

    def test_classe_is_invalid_sur_les_champs_en_erreur(self):
        formulaire = DemandeContactForm(donnees_valides(nom=''))
        formulaire.is_valid()
        self.assertIn('is-invalid', formulaire.fields['nom'].widget.attrs['class'])
        self.assertNotIn('is-invalid', formulaire.fields['email'].widget.attrs['class'])


# --- Page Contact ---------------------------------------------------------------------------

class PageContactTests(AvecFormationsMixin, TestCase):
    def test_page_accessible_avec_coordonnees(self):
        ParametresCentre.objects.create(nom='Centre', telephone='71000000', whatsapp='21612345678')
        reponse = self.client.get(URL_CONTACT)
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(URL_CONTACT, '/contact/')
        self.assertContains(reponse, 'tel:71000000')
        self.assertContains(reponse, 'https://wa.me/21612345678')
        self.assertContains(reponse, 'name="site_web"')

    def test_liste_des_formations_utilise_uuid_et_seulement_les_publiees(self):
        reponse = self.client.get(URL_CONTACT)
        self.assertContains(reponse, f'value="{self.publiee.uuid}"')
        self.assertNotContains(reponse, f'value="{self.publiee.pk}"')
        self.assertNotContains(reponse, 'Brouillon')

    def test_preremplissage_depuis_une_fiche_formation(self):
        reponse = self.client.get(URL_CONTACT, {'formation': self.publiee.slug})
        self.assertEqual(reponse.context['form'].initial['formation'], self.publiee.uuid)
        self.assertIn('Python', reponse.context['form'].initial['message'])

    def test_preremplissage_ignore_un_slug_inconnu_ou_non_publie(self):
        for slug in ('inexistant', self.brouillon.slug):
            with self.subTest(slug=slug):
                reponse = self.client.get(URL_CONTACT, {'formation': slug})
                self.assertEqual(reponse.status_code, 200)
                self.assertNotIn('formation', reponse.context['form'].initial)

    def test_fiche_formation_renvoie_vers_le_formulaire_prerempli(self):
        reponse = self.client.get(self.publiee.get_absolute_url())
        self.assertContains(reponse, f'/contact/?formation={self.publiee.slug}')

    def test_envoi_valide_enregistre_la_demande(self):
        reponse = self.client.post(URL_CONTACT, donnees_valides(formation=str(self.publiee.uuid)), follow=True)
        self.assertRedirects(reponse, URL_CONTACT)
        self.assertContains(reponse, MESSAGE_SUCCES)
        demande = DemandeContact.objects.get()
        self.assertEqual(demande.formation, self.publiee)
        self.assertEqual(demande.source, DemandeContact.Source.FORMULAIRE)
        self.assertEqual(demande.statut, DemandeContact.Statut.NOUVELLE)
        self.assertIsNone(demande.traitee_par)

    def test_statut_et_notes_ne_peuvent_pas_etre_forces_par_le_visiteur(self):
        self.client.post(URL_CONTACT, donnees_valides(statut='traitee', notes='piratage', source='telephone'))
        demande = DemandeContact.objects.get()
        self.assertEqual(demande.statut, DemandeContact.Statut.NOUVELLE)
        self.assertEqual(demande.source, DemandeContact.Source.FORMULAIRE)
        self.assertEqual(demande.notes, '')

    def test_envoi_invalide_reaffiche_le_formulaire(self):
        reponse = self.client.post(URL_CONTACT, donnees_valides(email='', telephone=''))
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'au moins un email ou un numéro')
        self.assertFalse(DemandeContact.objects.exists())

    def test_champ_piege_rempli_rien_n_est_enregistre(self):
        reponse = self.client.post(URL_CONTACT, donnees_valides(site_web='http://spam.example'), follow=True)
        # Même réponse qu'un envoi normal, pour ne pas révéler la protection au robot.
        self.assertRedirects(reponse, URL_CONTACT)
        self.assertContains(reponse, MESSAGE_SUCCES)
        self.assertFalse(DemandeContact.objects.exists())


# --- Permissions et administration ----------------------------------------------------------

class PermissionsCommercialTests(TestCase):
    def test_droits_des_groupes(self):
        gestionnaire = set(Group.objects.get(name=Roles.GESTIONNAIRE).permissions.values_list('codename', flat=True))
        administrateur = set(Group.objects.get(name=Roles.ADMINISTRATEUR).permissions.values_list('codename', flat=True))
        self.assertTrue({'view_demandecontact', 'add_demandecontact', 'change_demandecontact'} <= gestionnaire)
        self.assertNotIn('delete_demandecontact', gestionnaire)
        self.assertIn('delete_demandecontact', administrateur)
        for role in (Roles.FORMATEUR, Roles.CANDIDAT):
            with self.subTest(role=role):
                self.assertFalse(Group.objects.get(name=role).permissions.filter(content_type__app_label='commercial').exists())


class AdministrationDemandesTests(TestCase):
    def setUp(self):
        self.gestionnaire = get_user_model().objects.create_user(
            username='gest', email='gest@exemple.tn', password='MotDePasse!2026', is_staff=True,
        )
        self.gestionnaire.groups.add(Group.objects.get(name=Roles.GESTIONNAIRE))
        self.client.force_login(self.gestionnaire)
        self.demande = DemandeContact.objects.create(nom='Amira', email='amira@exemple.tn', message='Message original')

    def url_modification(self):
        return reverse('admin:commercial_demandecontact_change', args=[self.demande.pk])

    def test_pages_admin_et_suppression_interdite(self):
        self.assertEqual(self.client.get(reverse('admin:commercial_demandecontact_changelist')).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:commercial_demandecontact_add')).status_code, 200)
        self.assertEqual(self.client.get(self.url_modification()).status_code, 200)
        self.assertEqual(
            self.client.get(reverse('admin:commercial_demandecontact_delete', args=[self.demande.pk])).status_code, 403,
        )

    def test_contenu_de_la_demande_non_modifiable(self):
        self.client.post(self.url_modification(), {
            'nom': 'Nom modifié', 'message': 'Message modifié', 'email': 'autre@exemple.tn',
            'statut': DemandeContact.Statut.EN_COURS, 'notes': 'Rappeler lundi',
        })
        self.demande.refresh_from_db()
        self.assertEqual(self.demande.nom, 'Amira')
        self.assertEqual(self.demande.message, 'Message original')
        self.assertEqual(self.demande.email, 'amira@exemple.tn')
        self.assertEqual(self.demande.statut, DemandeContact.Statut.EN_COURS)
        self.assertEqual(self.demande.notes, 'Rappeler lundi')
        self.assertEqual(self.demande.traitee_par, self.gestionnaire)

    def test_action_marquer_traitee(self):
        # Date de modification placée dans le passé : sous Windows, l'horloge peut ne pas avancer
        # entre la création et l'action, ce qui rendait la comparaison instable.
        date_avant = timezone.now() - timedelta(hours=1)
        DemandeContact.objects.filter(pk=self.demande.pk).update(date_modification=date_avant)
        self.client.post(reverse('admin:commercial_demandecontact_changelist'), {
            'action': 'marquer_traitee', '_selected_action': [self.demande.pk],
        })
        self.demande.refresh_from_db()
        self.assertEqual(self.demande.statut, DemandeContact.Statut.TRAITEE)
        self.assertEqual(self.demande.traitee_par, self.gestionnaire)
        self.assertGreater(self.demande.date_modification, date_avant)

    def test_action_ne_remplace_pas_le_responsable_existant(self):
        collegue = get_user_model().objects.create_user(username='col', email='col@exemple.tn', password='x')
        DemandeContact.objects.filter(pk=self.demande.pk).update(traitee_par=collegue, statut=DemandeContact.Statut.EN_COURS)
        self.client.post(reverse('admin:commercial_demandecontact_changelist'), {
            'action': 'marquer_traitee', '_selected_action': [self.demande.pk],
        })
        self.demande.refresh_from_db()
        self.assertEqual(self.demande.statut, DemandeContact.Statut.TRAITEE)
        self.assertEqual(self.demande.traitee_par, collegue)

    def test_saisie_manuelle_d_une_demande_telephonique(self):
        reponse = self.client.get(reverse('admin:commercial_demandecontact_add'))
        self.assertEqual(reponse.context['adminform'].form.initial['source'], DemandeContact.Source.TELEPHONE)
        self.client.post(reverse('admin:commercial_demandecontact_add'), {
            'nom': 'Karim', 'telephone': '22 333 444', 'message': 'Appel reçu', 'source': 'telephone',
            'statut': 'nouvelle', 'notes': '',
        })
        self.assertTrue(DemandeContact.objects.filter(nom='Karim', source='telephone').exists())
