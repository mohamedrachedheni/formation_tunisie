"""Tests des emplacements photo : création par migration, compression, droits, affichage."""

import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import Roles

from .images import TAILLE_MAX_ENVOI, compresser_image
from .models import EmplacementPhoto, ParametresCentre

MEDIA_TEST = tempfile.mkdtemp(prefix='media_test_')
Utilisateur = get_user_model()
CLES_ATTENDUES = {'accueil_bandeau', 'accueil_presentation', 'accueil_etapes', 'accueil_appel_action', 'a_propos_principale'}


def image_envoyee(nom='photo.jpg', taille=(3000, 2000), format_image='JPEG', mode='RGB', exif_orientation=None):
    """Vraie image générée en mémoire, comme un envoi depuis un formulaire."""
    tampon = BytesIO()
    image = Image.new(mode, taille, (200, 30, 30, 128) if mode == 'RGBA' else (200, 30, 30))
    options = {}
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation  # balise Orientation
        options['exif'] = exif
    image.save(tampon, format=format_image, **options)
    return SimpleUploadedFile(nom, tampon.getvalue(), content_type=f'image/{format_image.lower()}')


def ouvrir(fichier_champ):
    fichier_champ.open('rb')
    try:
        image = Image.open(fichier_champ)
        image.load()
        return image
    finally:
        fichier_champ.close()


class MediaTemporaireMixin:
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEST, ignore_errors=True)


# --- Emplacements créés par migration --------------------------------------------------------

class EmplacementsCreesTests(TestCase):
    def test_emplacements_crees_par_la_migration(self):
        self.assertEqual(set(EmplacementPhoto.objects.values_list('cle', flat=True)), CLES_ATTENDUES)
        bandeau = EmplacementPhoto.objects.get(cle='accueil_bandeau')
        self.assertEqual(bandeau.page, EmplacementPhoto.Page.ACCUEIL)
        self.assertEqual(bandeau.largeur_max, 1920)
        self.assertFalse(bandeau.fichier)

    def test_cle_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            EmplacementPhoto.objects.create(cle='accueil_bandeau', page='accueil', libelle='Doublon')

    def test_ancien_champ_image_accueil_retire(self):
        self.assertNotIn('image_accueil', [champ.name for champ in ParametresCentre._meta.get_fields()])


# --- Compression et règles -------------------------------------------------------------------

@override_settings(MEDIA_ROOT=MEDIA_TEST)
class CompressionTests(MediaTemporaireMixin, TestCase):
    def setUp(self):
        self.emplacement = EmplacementPhoto.objects.get(cle='accueil_presentation')  # largeur max 1200

    def enregistrer(self, fichier, texte='Stagiaires en atelier'):
        self.emplacement.fichier = fichier
        self.emplacement.texte_alternatif = texte
        self.emplacement.save()
        return self.emplacement

    def test_redimensionnee_et_convertie_en_webp(self):
        envoi = image_envoyee(taille=(3000, 2000))
        taille_origine = envoi.size
        emplacement = self.enregistrer(envoi)
        self.assertTrue(emplacement.fichier.name.startswith('emplacements/'))
        self.assertTrue(emplacement.fichier.name.endswith('.webp'))
        image = ouvrir(emplacement.fichier)
        self.assertEqual(image.format, 'WEBP')
        self.assertEqual(image.size, (1200, 800))  # proportions conservées
        self.assertLess(emplacement.fichier.size, taille_origine)

    def test_petite_image_jamais_agrandie(self):
        image = ouvrir(self.enregistrer(image_envoyee(taille=(640, 480))).fichier)
        self.assertEqual(image.size, (640, 480))

    def test_orientation_du_telephone_appliquee(self):
        # Orientation EXIF 6 = photo prise téléphone tourné : l'image doit être redressée (portrait).
        image = ouvrir(self.enregistrer(image_envoyee(taille=(900, 600), exif_orientation=6)).fichier)
        self.assertEqual(image.size, (600, 900))
        self.assertNotIn(0x0112, image.getexif())  # métadonnées supprimées

    def test_transparence_conservee(self):
        image = ouvrir(self.enregistrer(image_envoyee(nom='logo.png', format_image='PNG', mode='RGBA', taille=(400, 200))).fichier)
        self.assertEqual(image.mode, 'RGBA')

    def test_fichier_non_image_refuse(self):
        faux = SimpleUploadedFile('photo.jpg', b'ceci n est pas une image', content_type='image/jpeg')
        with self.assertRaises(ValidationError):
            compresser_image(faux, 1200)

    def test_taille_maximale(self):
        trop_gros = SimpleUploadedFile('photo.jpg', b'0' * (TAILLE_MAX_ENVOI + 1), content_type='image/jpeg')
        self.emplacement.fichier = trop_gros
        self.emplacement.texte_alternatif = 'x'
        with self.assertRaises(ValidationError) as erreur:
            self.emplacement.full_clean()
        self.assertIn('fichier', erreur.exception.message_dict)

    def test_description_obligatoire_avec_une_photo(self):
        self.emplacement.fichier = image_envoyee()
        self.emplacement.texte_alternatif = ''
        with self.assertRaises(ValidationError) as erreur:
            self.emplacement.full_clean()
        self.assertIn('texte_alternatif', erreur.exception.message_dict)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.emplacement.save()

    def test_photo_remplacee_ancien_fichier_supprime(self):
        with self.captureOnCommitCallbacks(execute=True):
            ancien = self.enregistrer(image_envoyee()).fichier.name
        self.assertTrue(default_storage.exists(ancien))
        with self.captureOnCommitCallbacks(execute=True):
            nouveau = self.enregistrer(image_envoyee(nom='autre.jpg')).fichier.name
        self.assertNotEqual(ancien, nouveau)
        self.assertFalse(default_storage.exists(ancien))
        self.assertTrue(default_storage.exists(nouveau))

    def test_photo_retiree_fichier_supprime(self):
        with self.captureOnCommitCallbacks(execute=True):
            ancien = self.enregistrer(image_envoyee()).fichier.name
        emplacement = EmplacementPhoto.objects.get(pk=self.emplacement.pk)
        emplacement.fichier = ''
        emplacement.texte_alternatif = ''
        with self.captureOnCommitCallbacks(execute=True):
            emplacement.save()
        self.assertFalse(default_storage.exists(ancien))

    def test_modifier_la_description_garde_la_photo(self):
        with self.captureOnCommitCallbacks(execute=True):
            nom = self.enregistrer(image_envoyee()).fichier.name
        emplacement = EmplacementPhoto.objects.get(pk=self.emplacement.pk)
        emplacement.texte_alternatif = 'Nouvelle description'
        with self.captureOnCommitCallbacks(execute=True):
            emplacement.save()
        self.assertEqual(emplacement.fichier.name, nom)
        self.assertTrue(default_storage.exists(nom))


# --- Affichage -------------------------------------------------------------------------------

@override_settings(MEDIA_ROOT=MEDIA_TEST)
class AffichagePhotosTests(MediaTemporaireMixin, TestCase):
    def mettre_photo(self, cle, texte):
        emplacement = EmplacementPhoto.objects.get(cle=cle)
        emplacement.fichier = image_envoyee()
        emplacement.texte_alternatif = texte
        emplacement.save()
        return emplacement

    def test_sans_photo_la_page_garde_son_fond_par_defaut(self):
        reponse = self.client.get(reverse('core:accueil'))
        self.assertNotContains(reponse, '--image-fond')
        self.assertNotContains(reponse, 'photo-emplacement')
        self.assertContains(reponse, 'class="accueil-hero"')

    def test_photos_de_l_accueil(self):
        bandeau = self.mettre_photo('accueil_bandeau', 'Façade du centre')
        presentation = self.mettre_photo('accueil_presentation', 'Stagiaires en atelier')
        etapes = self.mettre_photo('accueil_etapes', 'Accueil des candidats')
        appel = self.mettre_photo('accueil_appel_action', 'Salle de formation')
        reponse = self.client.get(reverse('core:accueil'))
        self.assertContains(reponse, f"--image-fond: url('{bandeau.fichier.url}')")
        self.assertContains(reponse, 'accueil-hero avec-image')
        self.assertContains(reponse, 'Photo : Façade du centre')
        self.assertContains(reponse, f'src="{presentation.fichier.url}" alt="Stagiaires en atelier"')
        self.assertContains(reponse, 'cadre-arguments-sous-photo')
        self.assertContains(reponse, f'src="{etapes.fichier.url}" alt="Accueil des candidats"')
        self.assertContains(reponse, f"--image-fond: url('{appel.fichier.url}')")
        self.assertContains(reponse, 'appel-action avec-image')

    def test_photo_a_propos(self):
        self.assertNotContains(self.client.get(reverse('core:a_propos')), 'photo-emplacement')
        photo = self.mettre_photo('a_propos_principale', 'Équipe du centre')
        self.assertContains(self.client.get(reverse('core:a_propos')), f'src="{photo.fichier.url}" alt="Équipe du centre"')


# --- Droits : seul l'Administrateur change les photos ----------------------------------------

@override_settings(MEDIA_ROOT=MEDIA_TEST)
class DroitsPhotosTests(MediaTemporaireMixin, TestCase):
    def creer_membre(self, role):
        utilisateur = Utilisateur.objects.create_user(username=role, email=f'{role}@exemple.tn', password='x', is_staff=True)
        utilisateur.groups.add(Group.objects.get(name=role))
        return utilisateur

    def test_permissions_des_groupes(self):
        administrateur = Group.objects.get(name=Roles.ADMINISTRATEUR).permissions.values_list('codename', flat=True)
        self.assertIn('change_emplacementphoto', administrateur)
        for role in (Roles.GESTIONNAIRE, Roles.FORMATEUR, Roles.CANDIDAT):
            with self.subTest(role=role):
                self.assertFalse(Group.objects.get(name=role).permissions.filter(codename__endswith='emplacementphoto').exists())

    def test_administrateur_change_une_photo(self):
        self.client.force_login(self.creer_membre(Roles.ADMINISTRATEUR))
        emplacement = EmplacementPhoto.objects.get(cle='accueil_bandeau')
        url = reverse('admin:core_emplacementphoto_change', args=[emplacement.pk])
        self.assertEqual(self.client.get(reverse('admin:core_emplacementphoto_changelist')).status_code, 200)
        reponse = self.client.post(url, {'fichier': image_envoyee(), 'texte_alternatif': 'Façade du centre'})
        self.assertEqual(reponse.status_code, 302)
        emplacement.refresh_from_db()
        self.assertTrue(emplacement.fichier.name.endswith('.webp'))
        self.assertEqual(ouvrir(emplacement.fichier).width, 1920)

    def test_cle_et_libelle_non_modifiables(self):
        self.client.force_login(self.creer_membre(Roles.ADMINISTRATEUR))
        emplacement = EmplacementPhoto.objects.get(cle='accueil_bandeau')
        self.client.post(reverse('admin:core_emplacementphoto_change', args=[emplacement.pk]), {
            'cle': 'pirate', 'libelle': 'Pirate', 'texte_alternatif': '',
        })
        emplacement.refresh_from_db()
        self.assertEqual(emplacement.cle, 'accueil_bandeau')
        self.assertNotEqual(emplacement.libelle, 'Pirate')

    def test_formulaire_refuse_photo_sans_description(self):
        self.client.force_login(self.creer_membre(Roles.ADMINISTRATEUR))
        emplacement = EmplacementPhoto.objects.get(cle='accueil_bandeau')
        reponse = self.client.post(reverse('admin:core_emplacementphoto_change', args=[emplacement.pk]), {
            'fichier': image_envoyee(), 'texte_alternatif': '',
        })
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'Décrivez la photo')

    def test_ni_ajout_ni_suppression_meme_pour_le_superutilisateur(self):
        self.client.force_login(Utilisateur.objects.create_superuser(username='su', email='su@exemple.tn', password='x'))
        emplacement = EmplacementPhoto.objects.get(cle='accueil_bandeau')
        self.assertEqual(self.client.get(reverse('admin:core_emplacementphoto_add')).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:core_emplacementphoto_delete', args=[emplacement.pk])).status_code, 403)

    def test_gestionnaire_sans_acces(self):
        self.client.force_login(self.creer_membre(Roles.GESTIONNAIRE))
        emplacement = EmplacementPhoto.objects.get(cle='accueil_bandeau')
        self.assertEqual(self.client.get(reverse('admin:core_emplacementphoto_changelist')).status_code, 403)
        self.assertEqual(self.client.post(reverse('admin:core_emplacementphoto_change', args=[emplacement.pk]), {
            'fichier': image_envoyee(), 'texte_alternatif': 'x',
        }).status_code, 403)
        emplacement.refresh_from_db()
        self.assertFalse(emplacement.fichier)
