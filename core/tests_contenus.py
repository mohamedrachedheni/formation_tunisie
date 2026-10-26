"""Tests des contenus administrables du site : témoignages, partenaires, FAQ."""

import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import Roles

from .models import Partenaire, QuestionFrequente, Temoignage

URL_ACCUEIL = reverse('core:accueil')
URL_FAQ = reverse('core:faq')
MEDIA_TEST = tempfile.mkdtemp(prefix='media_test_')
Utilisateur = get_user_model()


def creer_temoignage(**champs):
    valeurs = {'nom': 'Amira B.', 'texte': 'Formation très concrète.', 'consentement_obtenu': True, 'est_publie': True}
    valeurs.update(champs)
    return Temoignage.objects.create(**valeurs)


def logo(nom='logo.png'):
    # Vraie image : les logos sont désormais ouverts et compressés à l'enregistrement.
    tampon = BytesIO()
    Image.new('RGBA', (300, 120), (0, 32, 91, 255)).save(tampon, format='PNG')
    return SimpleUploadedFile(nom, tampon.getvalue(), content_type='image/png')


# --- Témoignages ----------------------------------------------------------------------------

class TemoignageTests(TestCase):
    def test_publication_impossible_sans_consentement_en_base(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            creer_temoignage(consentement_obtenu=False, est_publie=True)

    def test_publication_impossible_sans_consentement_formulaire(self):
        with self.assertRaises(ValidationError) as erreur:
            Temoignage(nom='A', texte='t', consentement_obtenu=False, est_publie=True).full_clean()
        self.assertIn('est_publie', erreur.exception.message_dict)

    def test_brouillon_sans_consentement_autorise(self):
        temoignage = creer_temoignage(consentement_obtenu=False, est_publie=False)
        self.assertFalse(temoignage.est_publie)

    def test_note_entre_1_et_5(self):
        for note in (0, 6):
            with self.subTest(note=note), self.assertRaises(IntegrityError), transaction.atomic():
                creer_temoignage(note=note)
        self.assertEqual(creer_temoignage(note=5).note, 5)
        self.assertIsNone(creer_temoignage(note=None).note)

    def test_seuls_les_publies_et_dans_l_ordre(self):
        deuxieme = creer_temoignage(nom='Deuxième', ordre=2)
        premier = creer_temoignage(nom='Premier', ordre=1)
        creer_temoignage(nom='Brouillon', est_publie=False)
        self.assertEqual(list(Temoignage.objects.publies()), [premier, deuxieme])


class AccueilTemoignagesTests(TestCase):
    def test_section_masquee_sans_temoignage_publie(self):
        creer_temoignage(est_publie=False)
        self.assertNotContains(self.client.get(URL_ACCUEIL), 'Ils nous ont fait confiance')

    def test_temoignage_affiche_avec_note(self):
        creer_temoignage(nom='Karim J.', fonction='Comptable', formation_suivie='Comptabilité générale', note=4,
                         texte='Des formateurs disponibles.')
        reponse = self.client.get(URL_ACCUEIL)
        self.assertContains(reponse, 'Ils nous ont fait confiance')
        self.assertContains(reponse, 'Karim J.')
        self.assertContains(reponse, 'Comptable · Comptabilité générale')
        self.assertContains(reponse, 'Note : 4 sur 5')
        self.assertContains(reponse, 'bi-star-fill', count=4)

    def test_texte_echappe(self):
        creer_temoignage(texte='<script>alert(1)</script>')
        reponse = self.client.get(URL_ACCUEIL)
        self.assertNotContains(reponse, '<script>alert(1)</script>')
        self.assertContains(reponse, '&lt;script&gt;alert(1)&lt;/script&gt;')

    def test_douze_temoignages_au_maximum_dans_le_carrousel(self):
        for i in range(14):
            creer_temoignage(nom=f'Personne {i}', ordre=i)
        reponse = self.client.get(URL_ACCUEIL)
        self.assertEqual(len(reponse.context['temoignages']), 12)
        self.assertContains(reponse, 'carrousel-element', count=12)

    def test_carrousel_sur_une_ligne_avec_commandes(self):
        for i in range(5):
            creer_temoignage(nom=f'Personne {i}', ordre=i)
        reponse = self.client.get(URL_ACCUEIL)
        self.assertContains(reponse, 'data-carrousel aria-roledescription="carrousel"')
        self.assertContains(reponse, 'class="carrousel-piste"')
        self.assertContains(reponse, 'aria-label="1 sur 5"')
        for commande in ('data-carrousel-precedent', 'data-carrousel-pause', 'data-carrousel-suivant'):
            self.assertContains(reponse, commande)
        # L'ordre d'affichage est respecté dans la ligne.
        contenu = reponse.content.decode()
        self.assertLess(contenu.index('Personne 0'), contenu.index('Personne 4'))

    def test_un_seul_temoignage_sans_commandes(self):
        creer_temoignage()
        reponse = self.client.get(URL_ACCUEIL)
        self.assertContains(reponse, 'carrousel-element', count=1)
        self.assertNotContains(reponse, 'data-carrousel-commandes')


# --- Partenaires ----------------------------------------------------------------------------

@override_settings(MEDIA_ROOT=MEDIA_TEST)
class PartenaireTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEST, ignore_errors=True)

    def test_nom_unique_et_logo_obligatoire(self):
        Partenaire.objects.create(nom='Entreprise A', logo=logo())
        with self.assertRaises(IntegrityError), transaction.atomic():
            Partenaire.objects.create(nom='Entreprise A', logo=logo())
        with self.assertRaises(ValidationError) as erreur:
            Partenaire(nom='Sans logo').full_clean()
        self.assertIn('logo', erreur.exception.message_dict)

    def test_logo_nom_aleatoire(self):
        partenaire = Partenaire.objects.create(nom='Entreprise A', logo=logo('Logo Entreprise A.PNG'))
        self.assertTrue(partenaire.logo.name.startswith('partenaires/'))
        self.assertNotIn('Entreprise', partenaire.logo.name)

    def test_affichage_accueil(self):
        Partenaire.objects.create(nom='Entreprise A', logo=logo(), site_web='https://exemple.tn')
        Partenaire.objects.create(nom='Entreprise Cachée', logo=logo(), est_publie=False)
        reponse = self.client.get(URL_ACCUEIL)
        self.assertContains(reponse, 'Ils travaillent avec nous')
        self.assertContains(reponse, 'alt="Entreprise A"')
        self.assertContains(reponse, 'href="https://exemple.tn" target="_blank" rel="noopener noreferrer"')
        self.assertNotContains(reponse, 'Entreprise Cachée')

    def test_section_masquee_sans_partenaire(self):
        self.assertNotContains(self.client.get(URL_ACCUEIL), 'Ils travaillent avec nous')


# --- FAQ ------------------------------------------------------------------------------------

class FaqTests(TestCase):
    def test_question_unique(self):
        QuestionFrequente.objects.create(question='Comment payer ?', reponse='Sur place.')
        with self.assertRaises(IntegrityError), transaction.atomic():
            QuestionFrequente.objects.create(question='Comment payer ?', reponse='Autre.')

    def test_accueil_cinq_premieres_questions_et_lien(self):
        for i in range(7):
            QuestionFrequente.objects.create(question=f'Question {i} ?', reponse=f'Réponse {i}.', ordre=i)
        reponse = self.client.get(URL_ACCUEIL)
        self.assertContains(reponse, 'Questions fréquentes')
        self.assertContains(reponse, 'Question 4 ?')
        self.assertNotContains(reponse, 'Question 5 ?')
        self.assertContains(reponse, 'Toutes les questions')

    def test_accueil_sans_lien_si_cinq_questions_ou_moins(self):
        for i in range(5):
            QuestionFrequente.objects.create(question=f'Question {i} ?', reponse='r')
        self.assertNotContains(self.client.get(URL_ACCUEIL), 'Toutes les questions')

    def test_page_faq_seulement_les_publiees(self):
        QuestionFrequente.objects.create(question='Visible ?', reponse='Oui.\nSur deux lignes.')
        QuestionFrequente.objects.create(question='Cachée ?', reponse='Non.', est_publie=False)
        reponse = self.client.get(URL_FAQ)
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(URL_FAQ, '/faq/')
        self.assertContains(reponse, 'Visible ?')
        self.assertContains(reponse, 'Oui.<br>Sur deux lignes.')
        self.assertNotContains(reponse, 'Cachée ?')

    def test_page_faq_vide_et_lien_pied_de_page(self):
        reponse = self.client.get(URL_FAQ)
        self.assertContains(reponse, 'Aucune question pour le moment.')
        self.assertContains(reponse, f'href="{URL_FAQ}"')


# --- Permissions et administration ----------------------------------------------------------

class PermissionsContenusTests(TestCase):
    def droits(self, role):
        return set(Group.objects.get(name=role).permissions.filter(content_type__app_label='core').values_list('codename', flat=True))

    def test_droits_des_groupes(self):
        gestionnaire, administrateur = self.droits(Roles.GESTIONNAIRE), self.droits(Roles.ADMINISTRATEUR)
        for modele in ('temoignage', 'partenaire', 'questionfrequente'):
            with self.subTest(modele=modele):
                self.assertTrue({f'view_{modele}', f'add_{modele}', f'change_{modele}'} <= gestionnaire)
                self.assertNotIn(f'delete_{modele}', gestionnaire)
                self.assertIn(f'delete_{modele}', administrateur)
        self.assertIn('change_parametrescentre', administrateur)
        self.assertIn('view_parametrescentre', gestionnaire)
        self.assertNotIn('change_parametrescentre', gestionnaire)
        self.assertNotIn('delete_parametrescentre', administrateur)
        for role in (Roles.FORMATEUR, Roles.CANDIDAT):
            with self.subTest(role=role):
                self.assertEqual(self.droits(role), set())


class AdministrationContenusTests(TestCase):
    def setUp(self):
        self.gestionnaire = Utilisateur.objects.create_user(username='gest', email='gest@exemple.tn', password='x', is_staff=True)
        self.gestionnaire.groups.add(Group.objects.get(name=Roles.GESTIONNAIRE))
        self.client.force_login(self.gestionnaire)

    def test_pages_admin(self):
        temoignage = creer_temoignage()
        for url in (
            reverse('admin:core_temoignage_changelist'), reverse('admin:core_temoignage_add'),
            reverse('admin:core_temoignage_change', args=[temoignage.pk]),
            reverse('admin:core_partenaire_changelist'), reverse('admin:core_partenaire_add'),
            reverse('admin:core_questionfrequente_changelist'), reverse('admin:core_questionfrequente_add'),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:core_temoignage_delete', args=[temoignage.pk])).status_code, 403)

    def test_action_publier_ignore_les_temoignages_sans_consentement(self):
        avec = creer_temoignage(nom='Avec accord', est_publie=False)
        sans = creer_temoignage(nom='Sans accord', est_publie=False, consentement_obtenu=False)
        reponse = self.client.post(reverse('admin:core_temoignage_changelist'), {
            'action': 'publier', '_selected_action': [avec.pk, sans.pk],
        }, follow=True)
        avec.refresh_from_db()
        sans.refresh_from_db()
        self.assertTrue(avec.est_publie)
        self.assertFalse(sans.est_publie)
        self.assertContains(reponse, 'accord de la personne manquant')

    def test_formulaire_refuse_publication_sans_consentement(self):
        reponse = self.client.post(reverse('admin:core_temoignage_add'), {
            'nom': 'X', 'fonction': '', 'formation_suivie': '', 'texte': 'Bien.', 'note': '',
            'est_publie': 'on', 'ordre': 0,
        })
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'qu’avec l’accord de la personne')
        self.assertFalse(Temoignage.objects.exists())

    def test_gestionnaire_consulte_les_parametres_sans_les_modifier(self):
        from .models import ParametresCentre
        parametres = ParametresCentre.objects.create(nom='Centre')
        url = reverse('admin:core_parametrescentre_change', args=[parametres.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url, {'nom': 'Modifié'})
        parametres.refresh_from_db()
        self.assertEqual(parametres.nom, 'Centre')
