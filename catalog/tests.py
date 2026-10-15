import shutil
import tempfile
from decimal import Decimal
from urllib.parse import unquote

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Roles
from core.models import ParametresCentre

from .models import Categorie, DocumentFormation, Formation, ModuleProgramme

MEDIA_TEST = tempfile.mkdtemp(prefix='media_test_')


def creer_formation(categorie, titre='Développement Web Python', **champs):
    valeurs = {'resume': 'Apprendre Django.', 'duree_heures': 40, 'prix': Decimal('850.000'), 'est_publiee': True}
    valeurs.update(champs)
    return Formation.objects.create(categorie=categorie, titre=titre, **valeurs)


class CatalogueTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.informatique = Categorie.objects.create(nom='Informatique')
        cls.langues = Categorie.objects.create(nom='Langues')


class MediaTemporaireMixin:
    """Supprime les fichiers envoyés pendant les tests (dossier média temporaire)."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEST, ignore_errors=True)


# --- Modèles et contraintes ---------------------------------------------------------------

class SlugTests(CatalogueTestCase):
    def test_slug_genere_automatiquement(self):
        self.assertEqual(self.informatique.slug, 'informatique')
        formation = creer_formation(self.informatique, titre='Développement Web Python')
        self.assertEqual(formation.slug, 'developpement-web-python')

    def test_slug_saisi_conserve(self):
        formation = creer_formation(self.informatique, slug='django-avance')
        self.assertEqual(formation.slug, 'django-avance')

    def test_slug_formation_unique(self):
        creer_formation(self.informatique, titre='Excel')
        with self.assertRaises(IntegrityError), transaction.atomic():
            creer_formation(self.langues, titre='Excel')

    def test_nom_categorie_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Categorie.objects.create(nom='Informatique', slug='autre-slug')


class ContraintesFormationTests(CatalogueTestCase):
    def test_prix_negatif_refuse_par_la_base(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            creer_formation(self.informatique, prix=Decimal('-1'))

    def test_duree_nulle_refusee_par_la_base(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            creer_formation(self.informatique, duree_heures=0)

    def test_validation_formulaire_prix_et_duree(self):
        formation = Formation(categorie=self.informatique, titre='X', slug='x', resume='r', duree_heures=0, prix=Decimal('-5'))
        with self.assertRaises(ValidationError) as erreur:
            formation.full_clean()
        self.assertIn('prix', erreur.exception.message_dict)
        self.assertIn('duree_heures', erreur.exception.message_dict)

    def test_prix_conserve_les_millimes(self):
        formation = creer_formation(self.informatique, prix=Decimal('1250.375'))
        formation.refresh_from_db()
        self.assertEqual(formation.prix, Decimal('1250.375'))

    def test_categorie_avec_formations_protegee(self):
        creer_formation(self.informatique)
        with self.assertRaises(ProtectedError):
            self.informatique.delete()
        self.assertTrue(Categorie.objects.filter(pk=self.informatique.pk).exists())

    def test_uuid_unique_par_formation(self):
        f1 = creer_formation(self.informatique, titre='A')
        f2 = creer_formation(self.informatique, titre='B')
        self.assertNotEqual(f1.uuid, f2.uuid)


class ModuleProgrammeTests(CatalogueTestCase):
    def setUp(self):
        self.formation = creer_formation(self.informatique)

    def test_ordre_unique_par_formation(self):
        ModuleProgramme.objects.create(formation=self.formation, ordre=1, titre='Introduction')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ModuleProgramme.objects.create(formation=self.formation, ordre=1, titre='Doublon')

    def test_meme_ordre_autorise_dans_une_autre_formation(self):
        autre = creer_formation(self.informatique, titre='Autre')
        ModuleProgramme.objects.create(formation=self.formation, ordre=1, titre='A')
        ModuleProgramme.objects.create(formation=autre, ordre=1, titre='B')
        self.assertEqual(ModuleProgramme.objects.filter(ordre=1).count(), 2)

    def test_ordre_zero_refuse_par_la_base(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ModuleProgramme.objects.create(formation=self.formation, ordre=0, titre='Zéro')

    def test_duree_module_facultative_mais_positive(self):
        ModuleProgramme.objects.create(formation=self.formation, ordre=1, titre='Sans durée')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ModuleProgramme.objects.create(formation=self.formation, ordre=2, titre='Durée nulle', duree_heures=0)


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class DocumentFormationTests(MediaTemporaireMixin, CatalogueTestCase):
    def test_extension_interdite_refusee(self):
        formation = creer_formation(self.informatique)
        document = DocumentFormation(formation=formation, titre='Script', fichier=SimpleUploadedFile('virus.exe', b'MZ'))
        with self.assertRaises(ValidationError) as erreur:
            document.full_clean()
        self.assertIn('fichier', erreur.exception.message_dict)

    def test_nom_de_fichier_aleatoire(self):
        formation = creer_formation(self.informatique)
        document = DocumentFormation.objects.create(
            formation=formation, titre='Brochure', fichier=SimpleUploadedFile('Brochure Secrète.PDF', b'%PDF-1.4'),
        )
        self.assertTrue(document.fichier.name.startswith('formations/documents/'))
        self.assertTrue(document.fichier.name.endswith('.pdf'))
        self.assertNotIn('Brochure', document.fichier.name)


# --- Pages publiques ------------------------------------------------------------------------

@override_settings(MEDIA_ROOT=MEDIA_TEST)
class PagesCatalogueTests(MediaTemporaireMixin, CatalogueTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.publiee = creer_formation(cls.informatique, titre='Python Publiée')
        cls.brouillon = creer_formation(cls.informatique, titre='Brouillon Caché', est_publiee=False)
        cls.inactive = Categorie.objects.create(nom='Catégorie Inactive', est_active=False)
        cls.dans_inactive = creer_formation(cls.inactive, titre='Formation Masquée')
        cls.anglais = creer_formation(cls.langues, titre='Anglais Pro')

    def test_liste_affiche_seulement_les_formations_visibles(self):
        reponse = self.client.get(reverse('catalog:liste'))
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'Python Publiée')
        self.assertContains(reponse, 'Anglais Pro')
        self.assertNotContains(reponse, 'Brouillon Caché')
        self.assertNotContains(reponse, 'Formation Masquée')

    def test_filtre_par_categorie(self):
        reponse = self.client.get(reverse('catalog:liste'), {'categorie': 'langues'})
        self.assertContains(reponse, 'Anglais Pro')
        self.assertNotContains(reponse, 'Python Publiée')

    def test_filtre_categorie_inconnue_ou_inactive_404(self):
        for slug in ('inexistante', self.inactive.slug):
            with self.subTest(slug=slug):
                self.assertEqual(self.client.get(reverse('catalog:liste'), {'categorie': slug}).status_code, 404)

    def test_filtres_proposes_seulement_pour_categories_avec_formations_visibles(self):
        vide = Categorie.objects.create(nom='Sans Formation')
        categories = list(self.client.get(reverse('catalog:liste')).context['categories'])
        self.assertIn(self.informatique, categories)
        self.assertNotIn(vide, categories)
        self.assertNotIn(self.inactive, categories)

    def test_liste_vide(self):
        Formation.objects.update(est_publiee=False)
        self.assertContains(self.client.get(reverse('catalog:liste')), 'Aucune formation')

    def test_detail_formation_publiee_par_slug(self):
        reponse = self.client.get(self.publiee.get_absolute_url())
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(self.publiee.get_absolute_url(), '/formations/python-publiee/')
        self.assertContains(reponse, 'Python Publiée')
        self.assertContains(reponse, '850,000 DT')

    def test_detail_formation_non_visible_404(self):
        for formation in (self.brouillon, self.dans_inactive):
            with self.subTest(formation=formation.titre):
                self.assertEqual(self.client.get(formation.get_absolute_url()).status_code, 404)

    def test_detail_programme_dans_l_ordre(self):
        ModuleProgramme.objects.create(formation=self.publiee, ordre=2, titre='Module Deux')
        ModuleProgramme.objects.create(formation=self.publiee, ordre=1, titre='Module Un')
        contenu = self.client.get(self.publiee.get_absolute_url()).content.decode()
        self.assertLess(contenu.index('Module Un'), contenu.index('Module Deux'))

    def test_detail_affiche_seulement_les_documents_publics(self):
        DocumentFormation.objects.create(formation=self.publiee, titre='Brochure Publique',
                                         fichier=SimpleUploadedFile('b.pdf', b'%PDF'), est_public=True)
        DocumentFormation.objects.create(formation=self.publiee, titre='Support Réservé',
                                         fichier=SimpleUploadedFile('s.pdf', b'%PDF'), est_public=False)
        reponse = self.client.get(self.publiee.get_absolute_url())
        self.assertContains(reponse, 'Brochure Publique')
        self.assertNotContains(reponse, 'Support Réservé')

    def test_lien_whatsapp_prerempli(self):
        ParametresCentre.objects.create(nom='Centre', whatsapp='21612345678')
        reponse = self.client.get(self.publiee.get_absolute_url())
        self.assertContains(reponse, 'https://wa.me/21612345678?text=')
        self.assertIn('Python Publiée', unquote(reponse.context['lien_whatsapp_formation']))

    def test_pas_de_lien_whatsapp_sans_numero(self):
        reponse = self.client.get(self.publiee.get_absolute_url())
        self.assertNotIn('lien_whatsapp_formation', reponse.context)

    def test_aucun_id_numerique_dans_les_urls(self):
        reponse = self.client.get(reverse('catalog:liste'))
        self.assertNotContains(reponse, f'/formations/{self.publiee.pk}/')

    def test_pagination(self):
        for i in range(13):
            creer_formation(self.langues, titre=f'Formation Pagination {i:02d}')
        reponse = self.client.get(reverse('catalog:liste'))
        self.assertTrue(reponse.context['is_paginated'])
        self.assertEqual(len(reponse.context['formations']), 12)


# --- Permissions et administration ----------------------------------------------------------

class PermissionsCatalogueTests(TestCase):
    def test_droits_des_groupes(self):
        gestionnaire = Group.objects.get(name=Roles.GESTIONNAIRE)
        administrateur = Group.objects.get(name=Roles.ADMINISTRATEUR)
        droits_gestionnaire = set(gestionnaire.permissions.values_list('codename', flat=True))
        droits_admin = set(administrateur.permissions.values_list('codename', flat=True))
        for modele in ('categorie', 'formation', 'moduleprogramme', 'documentformation'):
            with self.subTest(modele=modele):
                self.assertTrue({f'view_{modele}', f'add_{modele}', f'change_{modele}'} <= droits_gestionnaire)
                self.assertNotIn(f'delete_{modele}', droits_gestionnaire)
                self.assertIn(f'delete_{modele}', droits_admin)

    def test_formateur_et_candidat_sans_droit_sur_le_catalogue(self):
        for role in (Roles.FORMATEUR, Roles.CANDIDAT):
            with self.subTest(role=role):
                self.assertFalse(Group.objects.get(name=role).permissions.filter(content_type__app_label='catalog').exists())

    def test_gestionnaire_peut_modifier_mais_pas_supprimer_dans_l_admin(self):
        utilisateur = get_user_model().objects.create_user(
            username='gest', email='gest@exemple.tn', password='MotDePasse!2026', is_staff=True,
        )
        utilisateur.groups.add(Group.objects.get(name=Roles.GESTIONNAIRE))
        categorie = Categorie.objects.create(nom='Informatique')
        formation = creer_formation(categorie)
        self.client.force_login(utilisateur)
        self.assertEqual(self.client.get(reverse('admin:catalog_formation_change', args=[formation.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:catalog_formation_delete', args=[formation.pk])).status_code, 403)

    def test_visiteur_non_connecte_redirige_hors_de_l_admin(self):
        reponse = self.client.get(reverse('admin:catalog_formation_changelist'))
        self.assertEqual(reponse.status_code, 302)


class AdministrationCatalogueTests(TestCase):
    def setUp(self):
        admin = get_user_model().objects.create_superuser(username='admin', email='admin@exemple.tn', password='MotDePasse!2026')
        self.client.force_login(admin)
        self.categorie = Categorie.objects.create(nom='Informatique')
        self.formation = creer_formation(self.categorie, est_publiee=False)

    def test_pages_admin(self):
        for url in (
            reverse('admin:catalog_categorie_changelist'),
            reverse('admin:catalog_formation_changelist'),
            reverse('admin:catalog_formation_add'),
            reverse('admin:catalog_formation_change', args=[self.formation.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_action_publier(self):
        self.client.post(reverse('admin:catalog_formation_changelist'), {
            'action': 'publier', '_selected_action': [self.formation.pk],
        })
        self.formation.refresh_from_db()
        self.assertTrue(self.formation.est_publiee)
