from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import Roles

Utilisateur = get_user_model()


class UtilisateurTests(TestCase):
    def creer(self, email='ali@exemple.tn', username='ali', password='MotDePasse!2026'):
        return Utilisateur.objects.create_user(username=username, email=email, password=password)

    def test_modele_utilisateur_personnalise(self):
        self.assertEqual(Utilisateur._meta.label, 'accounts.Utilisateur')
        self.assertEqual(Utilisateur.USERNAME_FIELD, 'email')

    def test_uuid_genere_automatiquement(self):
        self.assertIsNotNone(self.creer().uuid)

    def test_email_stocke_en_minuscules(self):
        self.assertEqual(self.creer(email='Ali@Exemple.TN').email, 'ali@exemple.tn')

    def test_email_unique_quelle_que_soit_la_casse(self):
        self.creer()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.creer(email='ALI@exemple.tn', username='ali2')

    def test_connexion_par_email_insensible_a_la_casse(self):
        utilisateur = self.creer()
        self.assertEqual(authenticate(username='ALI@Exemple.tn', password='MotDePasse!2026'), utilisateur)
        self.assertIsNone(authenticate(username='ali@exemple.tn', password='mauvais'))

    def test_creation_superutilisateur(self):
        admin = Utilisateur.objects.create_superuser(username='admin', email='admin@exemple.tn', password='MotDePasse!2026')
        self.assertTrue(admin.is_superuser and admin.is_staff)

    def test_a_le_role(self):
        utilisateur = self.creer()
        utilisateur.groups.add(Group.objects.get(name=Roles.GESTIONNAIRE))
        self.assertTrue(utilisateur.a_le_role(Roles.GESTIONNAIRE))
        self.assertFalse(utilisateur.a_le_role(Roles.ADMINISTRATEUR))


class GroupesRolesTests(TestCase):
    def test_groupes_crees_par_la_migration(self):
        self.assertEqual(set(Group.objects.values_list('name', flat=True)) & set(Roles.TOUS), set(Roles.TOUS))


class AdministrationUtilisateurTests(TestCase):
    def setUp(self):
        self.admin = Utilisateur.objects.create_superuser(username='admin', email='admin@exemple.tn', password='MotDePasse!2026')
        self.client.force_login(self.admin)

    def test_pages_admin_utilisateur(self):
        for url in (
            reverse('admin:accounts_utilisateur_changelist'),
            reverse('admin:accounts_utilisateur_add'),
            reverse('admin:accounts_utilisateur_change', args=[self.admin.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_ajout_utilisateur_depuis_admin(self):
        reponse = self.client.post(reverse('admin:accounts_utilisateur_add'), {
            'email': 'nouveau@exemple.tn',
            'username': 'nouveau',
            'first_name': 'Nouveau',
            'last_name': 'Compte',
            'password1': 'MotDePasse!2026',
            'password2': 'MotDePasse!2026',
            'usable_password': 'true',
        })
        self.assertEqual(reponse.status_code, 302)
        self.assertTrue(Utilisateur.objects.filter(email='nouveau@exemple.tn').exists())

    def test_admin_parametres_centre(self):
        self.assertEqual(self.client.get(reverse('admin:core_parametrescentre_add')).status_code, 200)
