"""Tests du niveau 3 côté comptes : connexion, limitation des tentatives, mot de passe oublié, invitations."""

import re
from datetime import datetime, timedelta
from unittest import mock
from urllib.parse import unquote

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from enrollments.models import Candidat
from trainers.models import Formateur

from .jetons import GenerateurInvitation, encoder_identifiant, generateur_invitation, utilisateur_depuis_identifiant
from .models import Roles

Utilisateur = get_user_model()
URL_CONNEXION = reverse('accounts:connexion')
MOT_DE_PASSE = 'Formation!2026'


def creer_compte(email='amira@exemple.tn', role=None, **champs):
    compte = Utilisateur.objects.create_user(username=email.split('@')[0], email=email, password=MOT_DE_PASSE, **champs)
    if role:
        compte.groups.add(Group.objects.get(name=role))
    return compte


class CacheVideMixin:
    def setUp(self):
        super().setUp()
        cache.clear()  # compteurs de tentatives de connexion


# --- Connexion -------------------------------------------------------------------------------

class ConnexionTests(CacheVideMixin, TestCase):
    def test_page_de_connexion(self):
        reponse = self.client.get(URL_CONNEXION)
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'Adresse email')
        self.assertContains(reponse, reverse('accounts:mot_de_passe_oublie'))

    def test_connexion_par_email_et_redirection_vers_l_espace(self):
        compte = creer_compte(role=Roles.CANDIDAT)
        Candidat.objects.create(nom='Ben Salah', prenom='Amira', telephone='98123456', utilisateur=compte)
        reponse = self.client.post(URL_CONNEXION, {'username': 'AMIRA@exemple.tn', 'password': MOT_DE_PASSE}, follow=True)
        self.assertRedirects(reponse, reverse('espaces:candidat'))

    def test_mauvais_mot_de_passe(self):
        creer_compte()
        reponse = self.client.post(URL_CONNEXION, {'username': 'amira@exemple.tn', 'password': 'faux'})
        self.assertContains(reponse, 'Email ou mot de passe incorrect.')
        self.assertNotIn('_auth_user_id', self.client.session)

    @override_settings(CONNEXION_ECHECS_MAX=3)
    def test_blocage_apres_trop_d_echecs_meme_avec_le_bon_mot_de_passe(self):
        creer_compte()
        for _ in range(3):
            self.client.post(URL_CONNEXION, {'username': 'amira@exemple.tn', 'password': 'faux'})
        reponse = self.client.post(URL_CONNEXION, {'username': 'amira@exemple.tn', 'password': MOT_DE_PASSE})
        self.assertContains(reponse, 'Trop de tentatives')
        self.assertNotIn('_auth_user_id', self.client.session)
        cache.clear()  # fin du blocage
        self.client.post(URL_CONNEXION, {'username': 'amira@exemple.tn', 'password': MOT_DE_PASSE})
        self.assertIn('_auth_user_id', self.client.session)

    def test_succes_remet_le_compteur_a_zero(self):
        creer_compte()
        self.client.post(URL_CONNEXION, {'username': 'amira@exemple.tn', 'password': 'faux'})
        self.client.post(URL_CONNEXION, {'username': 'amira@exemple.tn', 'password': MOT_DE_PASSE})
        self.assertIsNone(cache.get('connexion:email:amira@exemple.tn'))

    def test_deconnexion_uniquement_en_post(self):
        self.client.force_login(creer_compte())
        self.assertEqual(self.client.get(reverse('accounts:deconnexion')).status_code, 405)
        reponse = self.client.post(reverse('accounts:deconnexion'))
        self.assertRedirects(reponse, reverse('core:accueil'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_menu_connexion_ou_mon_espace(self):
        self.assertContains(self.client.get('/'), URL_CONNEXION)
        self.client.force_login(creer_compte())
        reponse = self.client.get('/')
        self.assertContains(reponse, 'Mon espace')
        self.assertNotContains(reponse, f'href="{URL_CONNEXION}"')


# --- Mot de passe oublié ---------------------------------------------------------------------

class MotDePasseOublieTests(CacheVideMixin, TestCase):
    def demander(self, email):
        return self.client.post(reverse('accounts:mot_de_passe_oublie'), {'email': email}, follow=True)

    def test_email_envoye_avec_lien_par_uuid(self):
        compte = creer_compte()
        reponse = self.demander('amira@exemple.tn')
        self.assertContains(reponse, 'Vérifiez votre messagerie')
        self.assertEqual(len(mail.outbox), 1)
        lien = re.search(r'https?://\S+', mail.outbox[0].body).group(0)
        self.assertIn(encoder_identifiant(compte), lien)
        # Nouveau mot de passe choisi via le lien
        reponse = self.client.get(lien, follow=True)
        self.client.post(reponse.request['PATH_INFO'], {'new_password1': 'NouveauMdp!2026', 'new_password2': 'NouveauMdp!2026'})
        compte.refresh_from_db()
        self.assertTrue(compte.check_password('NouveauMdp!2026'))

    def test_email_inconnu_meme_reponse_sans_envoi(self):
        reponse = self.demander('inconnu@exemple.tn')
        self.assertContains(reponse, 'Vérifiez votre messagerie')
        self.assertEqual(len(mail.outbox), 0)

    def test_compte_non_active_ne_recoit_pas_de_lien(self):
        compte = creer_compte()
        compte.set_unusable_password()
        compte.save()
        self.demander('amira@exemple.tn')
        self.assertEqual(len(mail.outbox), 0)  # il doit utiliser son lien d'invitation


# --- Invitations -----------------------------------------------------------------------------

class InvitationTests(CacheVideMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.gestionnaire = creer_compte('gest@exemple.tn', Roles.GESTIONNAIRE, is_staff=True)
        self.client.force_login(self.gestionnaire)
        self.candidat = Candidat.objects.create(nom='Ben Salah', prenom='Amira', telephone='98 123 456', email='amira@exemple.tn')

    def inviter(self, *fiches, url='admin:enrollments_candidat_changelist'):
        return self.client.post(reverse(url), {
            'action': 'creer_acces_espace', '_selected_action': [fiche.pk for fiche in fiches],
        })

    def lien_de(self, reponse):
        return re.search(r'value="(http[^"]+/compte/activer/[^"]+)"', reponse.content.decode()).group(1)

    def test_creation_du_compte_et_lien_d_activation(self):
        reponse = self.inviter(self.candidat)
        self.assertEqual(reponse.status_code, 200)
        self.candidat.refresh_from_db()
        compte = self.candidat.utilisateur
        self.assertEqual(compte.email, 'amira@exemple.tn')
        self.assertFalse(compte.has_usable_password())
        self.assertTrue(compte.a_le_role(Roles.CANDIDAT))
        lien = self.lien_de(reponse)
        self.assertIn(encoder_identifiant(compte), lien)
        self.assertNotIn(f'/{compte.pk}/', lien)
        # Bouton WhatsApp vers le numéro international, avec le lien dans le message
        whatsapp = re.search(r'href="(https://wa.me/[^"]+)"', reponse.content.decode()).group(1)
        self.assertTrue(whatsapp.startswith('https://wa.me/21698123456?text='))
        self.assertIn(lien, unquote(whatsapp.replace('&amp;', '&')))

    def test_activation_choix_du_mot_de_passe_et_connexion(self):
        lien = self.lien_de(self.inviter(self.candidat))
        self.client.logout()
        reponse = self.client.get(lien, follow=True)
        self.assertContains(reponse, 'Activer mon compte')
        reponse = self.client.post(reponse.request['PATH_INFO'], {
            'new_password1': 'MonMotDePasse!26', 'new_password2': 'MonMotDePasse!26',
        }, follow=True)
        self.assertRedirects(reponse, reverse('espaces:candidat'))
        self.assertContains(reponse, 'Votre compte est activé')
        self.candidat.refresh_from_db()
        self.assertTrue(self.candidat.utilisateur.check_password('MonMotDePasse!26'))

    def test_lien_a_usage_unique(self):
        lien = self.lien_de(self.inviter(self.candidat))
        self.client.logout()
        chemin = self.client.get(lien, follow=True).request['PATH_INFO']
        self.client.post(chemin, {'new_password1': 'MonMotDePasse!26', 'new_password2': 'MonMotDePasse!26'})
        self.client.logout()
        self.assertContains(self.client.get(lien, follow=True), 'Ce lien n’est plus valable')

    def test_lien_expire_apres_7_jours(self):
        lien = self.lien_de(self.inviter(self.candidat))
        self.client.logout()
        dans_8_jours = datetime.now() + timedelta(days=8)
        with mock.patch.object(GenerateurInvitation, '_now', return_value=dans_8_jours):
            self.assertContains(self.client.get(lien, follow=True), 'Ce lien n’est plus valable')

    def test_lien_altere_refuse(self):
        lien = self.lien_de(self.inviter(self.candidat))
        self.client.logout()
        self.assertContains(self.client.get(lien[:-3] + 'abc/', follow=True), 'Ce lien n’est plus valable')
        self.assertIsNone(utilisateur_depuis_identifiant('pas-un-uuid'))

    def test_jeton_d_invitation_inutilisable_pour_une_reinitialisation(self):
        self.inviter(self.candidat)
        self.candidat.refresh_from_db()
        compte = self.candidat.utilisateur
        jeton = generateur_invitation.make_token(compte)
        url = reverse('accounts:reinitialisation', kwargs={'uidb64': encoder_identifiant(compte), 'token': jeton})
        self.client.logout()
        self.assertContains(self.client.get(url, follow=True), 'Ce lien n’est plus valable')

    def test_sans_email_pas_de_compte(self):
        sans_email = Candidat.objects.create(nom='X', prenom='Y', telephone='98000001')
        reponse = self.inviter(sans_email)
        self.assertContains(reponse, 'Aucun email sur la fiche')
        sans_email.refresh_from_db()
        self.assertIsNone(sans_email.utilisateur)

    def test_email_deja_rattache_a_une_autre_fiche(self):
        self.inviter(self.candidat)
        doublon = Candidat.objects.create(nom='Autre', prenom='Personne', telephone='98000002', email='amira@exemple.tn')
        reponse = self.inviter(doublon)
        self.assertContains(reponse, 'déjà utilisé par le compte d’une autre fiche')
        doublon.refresh_from_db()
        self.assertIsNone(doublon.utilisateur)

    def test_compte_deja_active_pas_de_nouveau_lien(self):
        compte = creer_compte('amira2@exemple.tn', Roles.CANDIDAT)
        self.candidat.email = 'amira2@exemple.tn'
        self.candidat.utilisateur = compte
        self.candidat.save()
        reponse = self.inviter(self.candidat)
        self.assertContains(reponse, 'Compte déjà activé')
        self.assertNotContains(reponse, '/compte/activer/')

    def test_renouvellement_d_un_lien_non_utilise(self):
        premier = self.lien_de(self.inviter(self.candidat))
        second = self.lien_de(self.inviter(self.candidat))
        self.assertEqual(Utilisateur.objects.filter(email='amira@exemple.tn').count(), 1)
        self.assertTrue(premier and second)

    def test_invitation_d_un_formateur_actif_seulement(self):
        actif = Formateur.objects.create(nom='Trabelsi', prenom='Sami', email='sami@exemple.tn', telephone='22111222')
        inactif = Formateur.objects.create(nom='Inactif', prenom='Nadia', email='nadia@exemple.tn', est_actif=False)
        reponse = self.inviter(actif, inactif, url='admin:trainers_formateur_changelist')
        self.assertContains(reponse, 'Sami Trabelsi')
        actif.refresh_from_db()
        inactif.refresh_from_db()
        self.assertTrue(actif.utilisateur.a_le_role(Roles.FORMATEUR))
        self.assertIsNone(inactif.utilisateur)

    def test_action_refusee_sans_droit_de_modification(self):
        lecteur = creer_compte('lecteur@exemple.tn', is_staff=True)
        from django.contrib.auth.models import Permission
        lecteur.user_permissions.add(Permission.objects.get(codename='view_candidat'))
        self.client.force_login(lecteur)
        self.inviter(self.candidat)
        self.candidat.refresh_from_db()
        self.assertIsNone(self.candidat.utilisateur)
