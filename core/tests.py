from urllib.parse import unquote

from django import forms
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .forms import FormulairePublicMixin
from .models import ParametresCentre
from .validators import normaliser_telephone


class ParametresCentreTests(TestCase):
    def test_creation_et_lecture(self):
        self.assertIsNone(ParametresCentre.obtenir())
        parametres = ParametresCentre.objects.create(nom='Centre Test')
        self.assertIsNotNone(parametres.uuid)
        self.assertEqual(ParametresCentre.obtenir(), parametres)

    def test_second_enregistrement_refuse_sans_ecraser_le_premier(self):
        premier = ParametresCentre.objects.create(nom='Centre Test')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ParametresCentre.objects.create(nom='Autre centre')
        premier.refresh_from_db()
        self.assertEqual(premier.nom, 'Centre Test')
        self.assertEqual(ParametresCentre.objects.count(), 1)

    def test_clean_refuse_un_second_enregistrement(self):
        ParametresCentre.objects.create(nom='Centre Test')
        with self.assertRaises(ValidationError):
            ParametresCentre(nom='Autre centre').full_clean()

    def test_modification_conserve_uuid(self):
        parametres = ParametresCentre.objects.create(nom='Centre Test')
        uuid_initial = parametres.uuid
        parametres.nom = 'Nouveau nom'
        parametres.save()
        parametres.refresh_from_db()
        self.assertEqual(parametres.uuid, uuid_initial)
        self.assertEqual(parametres.nom, 'Nouveau nom')

    def test_contrainte_check_refuse_verrou_faux(self):
        # Contournement volontaire : seule la contrainte CHECK de la base protège ici.
        with self.assertRaises(IntegrityError), transaction.atomic():
            ParametresCentre.objects.create(nom='Interdit', verrou=False)

    def test_lien_whatsapp(self):
        self.assertEqual(ParametresCentre(nom='C', whatsapp='21612345678').lien_whatsapp, 'https://wa.me/21612345678')
        self.assertEqual(ParametresCentre(nom='C').lien_whatsapp, '')


class OutilsCommunsTests(TestCase):
    def test_normaliser_telephone(self):
        cas = {
            '98 123 456': '98123456',
            '98-123-456': '98123456',
            '98.123.456': '98123456',
            '+216 98 123 456': '98123456',
            '00216 98 123 456': '98123456',
            '+33 6 12 34 56 78': '+33612345678',
            '0033612345678': '+33612345678',
            '': '',
            None: '',
        }
        for saisie, attendu in cas.items():
            with self.subTest(saisie=saisie):
                self.assertEqual(normaliser_telephone(saisie), attendu)

    def test_lien_whatsapp_avec_message_encode(self):
        centre = ParametresCentre(nom='C', whatsapp='21612345678')
        lien = centre.lien_whatsapp_avec_message('Bonjour « Excel » & co')
        self.assertTrue(lien.startswith('https://wa.me/21612345678?text='))
        self.assertEqual(unquote(lien.split('?text=')[1]), 'Bonjour « Excel » & co')
        self.assertEqual(ParametresCentre(nom='C').lien_whatsapp_avec_message('x'), '')

    def test_formulaire_public_champ_piege_et_classes(self):
        class Formulaire(FormulairePublicMixin, forms.Form):
            nom = forms.CharField()
            choix = forms.ChoiceField(choices=[('a', 'A')])
            accord = forms.BooleanField()

        formulaire = Formulaire({'nom': '', 'choix': 'a', 'accord': 'on', 'site_web': 'http://spam'})
        self.assertIn('site_web', formulaire.fields)
        self.assertFalse(formulaire.is_valid())
        self.assertEqual(formulaire.fields['nom'].widget.attrs['class'], 'form-control is-invalid')
        self.assertEqual(formulaire.fields['choix'].widget.attrs['class'], 'form-select')
        self.assertEqual(formulaire.fields['accord'].widget.attrs['class'], 'form-check-input')
        self.assertNotIn('class', formulaire.fields['site_web'].widget.attrs)
        self.assertTrue(Formulaire({'nom': 'x', 'choix': 'a', 'accord': 'on', 'site_web': 'x'}).is_valid())
        robot = Formulaire({'nom': 'x', 'choix': 'a', 'accord': 'on', 'site_web': 'x'})
        robot.is_valid()
        self.assertTrue(robot.est_spam())


class PagesVitrineTests(TestCase):
    # La page Contact est testée dans l'application `commercial`.
    PAGES = ('core:accueil', 'core:a_propos')

    def test_pages_accessibles_sans_parametres(self):
        for nom in self.PAGES:
            with self.subTest(page=nom):
                self.assertEqual(self.client.get(reverse(nom)).status_code, 200)

    def test_pages_affichent_les_parametres_du_centre(self):
        ParametresCentre.objects.create(nom='Centre Excellence', telephone='71000000', whatsapp='21612345678')
        for nom in self.PAGES:
            with self.subTest(page=nom):
                reponse = self.client.get(reverse(nom))
                self.assertContains(reponse, 'Centre Excellence')
                self.assertContains(reponse, 'https://wa.me/21612345678')
