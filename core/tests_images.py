"""Compression automatique de toutes les images du site (champ ImageCompresseeField)."""

import shutil
import tempfile
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Categorie, Formation
from trainers.models import Formateur

from .champs import ImageCompresseeField
from .images import TAILLE_MAX_ENVOI, valider_taille_image
from .models import EmplacementPhoto, ParametresCentre, Partenaire, Temoignage
from .tests_photos import image_envoyee, ouvrir

MEDIA_TEST = tempfile.mkdtemp(prefix='media_test_')


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class CompressionDesImagesTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEST, ignore_errors=True)

    def verifier(self, champ_fichier, dossier, largeur_attendue, hauteur_attendue):
        self.assertTrue(champ_fichier.name.startswith(dossier), champ_fichier.name)
        self.assertTrue(champ_fichier.name.endswith('.webp'))
        image = ouvrir(champ_fichier)
        self.assertEqual(image.format, 'WEBP')
        self.assertEqual(image.size, (largeur_attendue, hauteur_attendue))
        return image

    def test_image_de_formation(self):
        categorie = Categorie.objects.create(nom='Informatique')
        formation = Formation.objects.create(
            categorie=categorie, titre='Python', resume='r', duree_heures=10, prix=Decimal('100'),
            image=image_envoyee(nom='Affiche Python.JPG', taille=(3000, 2000)),
        )
        self.verifier(formation.image, 'formations/images/', 1200, 800)
        self.assertNotIn('Affiche', formation.image.name)

    def test_photo_de_formateur(self):
        formateur = Formateur.objects.create(nom='Trabelsi', prenom='Sami', photo=image_envoyee(taille=(2000, 3000)))
        self.verifier(formateur.photo, 'formateurs/photos/', 400, 600)

    def test_photo_de_temoignage(self):
        temoignage = Temoignage.objects.create(nom='A', texte='t', photo=image_envoyee(taille=(1000, 1000)))
        self.verifier(temoignage.photo, 'temoignages/', 200, 200)

    def test_logo_de_partenaire_garde_sa_transparence(self):
        partenaire = Partenaire.objects.create(
            nom='Entreprise', logo=image_envoyee(nom='logo.png', format_image='PNG', mode='RGBA', taille=(1600, 400)),
        )
        image = self.verifier(partenaire.logo, 'partenaires/', 400, 100)
        self.assertEqual(image.mode, 'RGBA')

    def test_logo_du_centre(self):
        centre = ParametresCentre.objects.create(
            nom='Centre', logo=image_envoyee(nom='logo.png', format_image='PNG', mode='RGBA', taille=(1024, 256)),
        )
        self.verifier(centre.logo, 'centre/', 512, 128)

    def test_petite_image_jamais_agrandie(self):
        formateur = Formateur.objects.create(nom='A', prenom='B', photo=image_envoyee(taille=(150, 150)))
        self.verifier(formateur.photo, 'formateurs/photos/', 150, 150)

    def test_image_remplacee_ancien_fichier_supprime(self):
        with self.captureOnCommitCallbacks(execute=True):
            formateur = Formateur.objects.create(nom='A', prenom='B', photo=image_envoyee())
        ancien = formateur.photo.name
        formateur = Formateur.objects.get(pk=formateur.pk)
        formateur.photo = image_envoyee(nom='nouvelle.jpg')
        with self.captureOnCommitCallbacks(execute=True):
            formateur.save()
        self.assertFalse(default_storage.exists(ancien))
        self.assertTrue(default_storage.exists(formateur.photo.name))

    def test_autre_modification_garde_l_image(self):
        with self.captureOnCommitCallbacks(execute=True):
            formateur = Formateur.objects.create(nom='A', prenom='B', photo=image_envoyee())
        nom = formateur.photo.name
        formateur = Formateur.objects.get(pk=formateur.pk)
        formateur.specialite = 'Réseaux'
        with self.captureOnCommitCallbacks(execute=True):
            formateur.save()
        self.assertEqual(formateur.photo.name, nom)
        self.assertTrue(default_storage.exists(nom))

    def test_echec_de_l_enregistrement_ne_supprime_rien(self):
        # Si l'enregistrement échoue (transaction annulée), l'ancienne image doit rester sur le disque.
        with self.captureOnCommitCallbacks(execute=True):
            formateur = Formateur.objects.create(nom='A', prenom='B', photo=image_envoyee())
        ancien = formateur.photo.name
        formateur = Formateur.objects.get(pk=formateur.pk)
        formateur.photo = image_envoyee(nom='nouvelle.jpg')
        with self.captureOnCommitCallbacks(execute=True) as rappels:
            try:
                from django.db import transaction
                with transaction.atomic():
                    formateur.save()
                    raise RuntimeError('échec simulé')
            except RuntimeError:
                pass
        self.assertEqual(rappels, [])
        self.assertTrue(default_storage.exists(ancien))

    def test_taille_maximale_sur_tous_les_champs(self):
        trop_gros = SimpleUploadedFile('photo.jpg', b'0' * (TAILLE_MAX_ENVOI + 1), content_type='image/jpeg')
        with self.assertRaises(ValidationError) as erreur:
            Formateur(nom='A', prenom='B', photo=trop_gros).full_clean()
        self.assertIn('photo', erreur.exception.message_dict)

    def test_tous_les_champs_image_sont_compresses(self):
        # Garde-fou : toute nouvelle image ajoutée au projet doit utiliser ImageCompresseeField.
        from django.apps import apps
        from django.db.models import ImageField
        champs = [
            f'{modele._meta.label}.{champ.name}'
            for modele in apps.get_models() if modele._meta.app_label in ('core', 'catalog', 'trainers', 'commercial', 'enrollments', 'accounts')
            for champ in modele._meta.concrete_fields if isinstance(champ, ImageField)
        ]
        non_compresses = [nom for nom in champs if not isinstance(apps.get_model(nom.rsplit('.', 1)[0])._meta.get_field(nom.rsplit('.', 1)[1]), ImageCompresseeField)]
        self.assertEqual(non_compresses, [])
        self.assertEqual(len(champs), 6)


class ChampImageCompresseeTests(TestCase):
    def test_serialisation_pour_les_migrations(self):
        champ = ImageCompresseeField(upload_to='x', largeur_max=400)
        _, chemin, _, kwargs = champ.deconstruct()
        self.assertEqual(chemin, 'core.champs.ImageCompresseeField')
        self.assertEqual(kwargs['largeur_max'], 400)
        self.assertNotIn('validators', kwargs)
        self.assertIn(valider_taille_image, champ.validators)
        _, _, _, kwargs = ImageCompresseeField(upload_to='x', champ_largeur='largeur_max').deconstruct()
        self.assertEqual(kwargs['champ_largeur'], 'largeur_max')

    def test_largeur_par_emplacement(self):
        champ = EmplacementPhoto._meta.get_field('fichier')
        self.assertEqual(champ.largeur_pour(EmplacementPhoto(largeur_max=1400)), 1400)


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class EnvoiDepuisAdministrationTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEST, ignore_errors=True)

    def test_photo_de_formateur_envoyee_depuis_l_admin(self):
        from django.contrib.auth import get_user_model
        admin = get_user_model().objects.create_superuser(username='su', email='su@exemple.tn', password='x')
        self.client.force_login(admin)
        reponse = self.client.post(reverse('admin:trainers_formateur_add'), {
            'prenom': 'Sami', 'nom': 'Trabelsi', 'specialite': '', 'biographie': '', 'telephone': '', 'email': '',
            'est_actif': 'on', 'utilisateur': '', 'photo': image_envoyee(taille=(2400, 2400)),
        })
        self.assertEqual(reponse.status_code, 302)
        photo = Formateur.objects.get().photo
        self.assertEqual(ouvrir(photo).size, (400, 400))
