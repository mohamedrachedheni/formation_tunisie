import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Roles
from core.fichiers import CheminAleatoire

from .models import Formateur

MEDIA_TEST = tempfile.mkdtemp(prefix='media_test_')
Utilisateur = get_user_model()


def creer_formateur(**champs):
    valeurs = {'nom': 'Trabelsi', 'prenom': 'Sami', 'specialite': 'Développement web'}
    valeurs.update(champs)
    return Formateur.objects.create(**valeurs)


# --- Modèle et contraintes ------------------------------------------------------------------

class FormateurModeleTests(TestCase):
    def test_creation_sans_compte_et_valeurs_par_defaut(self):
        formateur = creer_formateur()
        self.assertIsNone(formateur.utilisateur)
        self.assertTrue(formateur.est_actif)
        self.assertFalse(formateur.est_visible_site)
        self.assertIsNotNone(formateur.uuid)
        self.assertEqual(str(formateur), 'Sami Trabelsi')

    def test_email_vide_stocke_null_et_plusieurs_formateurs_sans_email(self):
        premier = creer_formateur(email='')
        creer_formateur(nom='Gharbi', email=None)
        premier.refresh_from_db()
        self.assertIsNone(premier.email)
        self.assertEqual(Formateur.objects.filter(email__isnull=True).count(), 2)

    def test_email_unique_quelle_que_soit_la_casse(self):
        creer_formateur(email='Sami@Exemple.tn')
        self.assertTrue(Formateur.objects.filter(email='sami@exemple.tn').exists())
        with self.assertRaises(IntegrityError), transaction.atomic():
            creer_formateur(nom='Autre', email='SAMI@exemple.tn')

    def test_un_compte_pour_un_seul_formateur(self):
        compte = Utilisateur.objects.create_user(username='sami', email='sami@exemple.tn', password='x')
        creer_formateur(utilisateur=compte)
        with self.assertRaises(IntegrityError), transaction.atomic():
            creer_formateur(nom='Autre', utilisateur=compte)

    def test_suppression_du_compte_conserve_le_formateur(self):
        compte = Utilisateur.objects.create_user(username='sami', email='sami@exemple.tn', password='x')
        formateur = creer_formateur(utilisateur=compte)
        compte.delete()
        formateur.refresh_from_db()
        self.assertIsNone(formateur.utilisateur)

    def test_base_refuse_un_formateur_inactif_visible(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            creer_formateur(est_actif=False, est_visible_site=True)

    def test_validation_formateur_inactif_visible(self):
        formateur = Formateur(nom='A', prenom='B', est_actif=False, est_visible_site=True)
        with self.assertRaises(ValidationError) as erreur:
            formateur.full_clean()
        self.assertIn('est_visible_site', erreur.exception.message_dict)

    def test_telephone_invalide(self):
        with self.assertRaises(ValidationError) as erreur:
            Formateur(nom='A', prenom='B', telephone='12ab').full_clean()
        self.assertIn('telephone', erreur.exception.message_dict)

    def test_querysets_actifs_et_visibles(self):
        visible = creer_formateur(nom='Visible', est_visible_site=True)
        actif = creer_formateur(nom='Actif')
        inactif = creer_formateur(nom='Inactif', est_actif=False)
        self.assertEqual(set(Formateur.objects.actifs()), {visible, actif})
        self.assertEqual(list(Formateur.objects.visibles()), [visible])
        self.assertNotIn(inactif, Formateur.objects.actifs())


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class FichiersFormateurTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEST, ignore_errors=True)

    def test_cv_avec_nom_aleatoire(self):
        formateur = creer_formateur(cv=SimpleUploadedFile('CV Sami Trabelsi.PDF', b'%PDF-1.4'))
        self.assertTrue(formateur.cv.name.startswith('formateurs/cv/'))
        self.assertTrue(formateur.cv.name.endswith('.pdf'))
        self.assertNotIn('Trabelsi', formateur.cv.name)

    def test_extension_de_cv_interdite(self):
        formateur = Formateur(nom='A', prenom='B', cv=SimpleUploadedFile('cv.exe', b'MZ'))
        with self.assertRaises(ValidationError) as erreur:
            formateur.full_clean()
        self.assertIn('cv', erreur.exception.message_dict)

    def test_chemin_aleatoire_serialisable_pour_les_migrations(self):
        chemin = CheminAleatoire('formateurs/photos/')
        self.assertEqual(chemin.deconstruct(), ('core.fichiers.CheminAleatoire', ('formateurs/photos/',), {}))
        self.assertEqual(chemin, CheminAleatoire('formateurs/photos'))
        self.assertNotEqual(chemin(None, 'a.JPG'), chemin(None, 'a.JPG'))


# --- Permissions et administration ----------------------------------------------------------

class PermissionsFormateurTests(TestCase):
    def test_droits_des_groupes(self):
        gestionnaire = set(Group.objects.get(name=Roles.GESTIONNAIRE).permissions.values_list('codename', flat=True))
        administrateur = set(Group.objects.get(name=Roles.ADMINISTRATEUR).permissions.values_list('codename', flat=True))
        self.assertTrue({'view_formateur', 'add_formateur', 'change_formateur'} <= gestionnaire)
        self.assertNotIn('delete_formateur', gestionnaire)
        self.assertIn('delete_formateur', administrateur)
        for role in (Roles.FORMATEUR, Roles.CANDIDAT):
            with self.subTest(role=role):
                self.assertFalse(Group.objects.get(name=role).permissions.filter(content_type__app_label='trainers').exists())


class AdministrationFormateurTests(TestCase):
    def setUp(self):
        self.admin = Utilisateur.objects.create_superuser(username='admin', email='admin@exemple.tn', password='x')
        self.formateur = creer_formateur()

    def donnees_formulaire(self, **champs):
        donnees = {'prenom': 'Sami', 'nom': 'Trabelsi', 'specialite': '', 'biographie': '', 'telephone': '',
                   'email': '', 'est_actif': 'on', 'utilisateur': ''}
        donnees.update(champs)
        return donnees

    def test_pages_admin(self):
        self.client.force_login(self.admin)
        for url in (
            reverse('admin:trainers_formateur_changelist'),
            reverse('admin:trainers_formateur_add'),
            reverse('admin:trainers_formateur_change', args=[self.formateur.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_rattacher_un_compte_donne_le_role_formateur(self):
        self.client.force_login(self.admin)
        compte = Utilisateur.objects.create_user(username='sami', email='sami@exemple.tn', password='x')
        reponse = self.client.post(
            reverse('admin:trainers_formateur_change', args=[self.formateur.pk]),
            self.donnees_formulaire(utilisateur=compte.pk),
        )
        self.assertEqual(reponse.status_code, 302)
        self.formateur.refresh_from_db()
        self.assertEqual(self.formateur.utilisateur, compte)
        self.assertTrue(compte.a_le_role(Roles.FORMATEUR))

    def test_formulaire_refuse_inactif_visible(self):
        self.client.force_login(self.admin)
        reponse = self.client.post(
            reverse('admin:trainers_formateur_change', args=[self.formateur.pk]),
            self.donnees_formulaire(est_actif='', est_visible_site='on'),
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'Un formateur inactif ne peut pas être visible')

    def test_action_desactiver(self):
        self.client.force_login(self.admin)
        Formateur.objects.filter(pk=self.formateur.pk).update(est_visible_site=True)
        self.client.post(reverse('admin:trainers_formateur_changelist'), {
            'action': 'desactiver', '_selected_action': [self.formateur.pk],
        })
        self.formateur.refresh_from_db()
        self.assertFalse(self.formateur.est_actif)
        self.assertFalse(self.formateur.est_visible_site)

    def test_gestionnaire_sans_suppression_ni_rattachement_de_compte(self):
        gestionnaire = Utilisateur.objects.create_user(username='gest', email='gest@exemple.tn', password='x', is_staff=True)
        gestionnaire.groups.add(Group.objects.get(name=Roles.GESTIONNAIRE))
        self.client.force_login(gestionnaire)
        url_modification = reverse('admin:trainers_formateur_change', args=[self.formateur.pk])
        reponse = self.client.get(url_modification)
        self.assertEqual(reponse.status_code, 200)
        self.assertIn('utilisateur', reponse.context['adminform'].readonly_fields)
        self.assertEqual(
            self.client.get(reverse('admin:trainers_formateur_delete', args=[self.formateur.pk])).status_code, 403,
        )
        # Une tentative d'envoi du champ utilisateur est ignorée.
        compte = Utilisateur.objects.create_user(username='x', email='x@exemple.tn', password='x')
        self.client.post(url_modification, self.donnees_formulaire(utilisateur=compte.pk, specialite='Réseaux'))
        self.formateur.refresh_from_db()
        self.assertEqual(self.formateur.specialite, 'Réseaux')
        self.assertIsNone(self.formateur.utilisateur)
