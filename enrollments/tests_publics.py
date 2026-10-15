"""Tests des pages publiques d'enrollments : sessions visibles, pré-inscription, WhatsApp."""

from datetime import date
from decimal import Decimal
from unittest import mock
from urllib.parse import unquote

from django.test import TestCase
from django.urls import reverse

from catalog.models import Categorie, Formation
from core.models import ParametresCentre

from . import services
from .models import Candidat, Inscription, Session
from .views import MESSAGE_SUCCES


class PublicMixin:
    @classmethod
    def setUpTestData(cls):
        cls.categorie = Categorie.objects.create(nom='Bureautique')
        cls.formation = Formation.objects.create(
            categorie=cls.categorie, titre='Excel Avancé', resume='r', duree_heures=20,
            prix=Decimal('400.000'), est_publiee=True,
        )
        cls.session = Session.objects.create(
            formation=cls.formation, code='EXCEL-NOV', date_debut=date(2026, 11, 2), date_fin=date(2026, 11, 20),
            places_max=2, statut=Session.Statut.OUVERTE, est_publiee=True, lieu='Salle A',
        )

    def url_inscription(self, session=None):
        return reverse('enrollments:inscription', kwargs={'uuid': (session or self.session).uuid})

    def donnees(self, **champs):
        valeurs = {'prenom': 'Amira', 'nom': 'Ben Salah', 'telephone': '98 123 456', 'email': 'amira@exemple.tn',
                   'cin': '', 'date_naissance': '', 'gouvernorat': 'sfax', 'niveau_etudes': '', 'profession': '',
                   'message': '', 'consentement': 'on', 'site_web': ''}
        valeurs.update(champs)
        return valeurs


# --- Visibilité des sessions ----------------------------------------------------------------

class VisibiliteSessionsTests(PublicMixin, TestCase):
    def test_regle_de_visibilite(self):
        cachees = {
            'non publiée': {'est_publiee': False},
            'planifiée': {'statut': Session.Statut.PLANIFIEE},
            'en cours': {'statut': Session.Statut.EN_COURS},
            'annulée': {'statut': Session.Statut.ANNULEE},
        }
        for libelle, champs in cachees.items():
            with self.subTest(libelle):
                session = Session.objects.create(
                    formation=self.formation, date_debut=date(2026, 12, 1), date_fin=date(2026, 12, 2), places_max=5,
                    **{'statut': Session.Statut.OUVERTE, 'est_publiee': True, **champs},
                )
                self.assertNotIn(session, Session.objects.visibles())
        self.assertIn(self.session, Session.objects.visibles())

    def test_session_cachee_si_formation_non_visible(self):
        Formation.objects.filter(pk=self.formation.pk).update(est_publiee=False)
        self.assertFalse(Session.objects.visibles().exists())
        Formation.objects.filter(pk=self.formation.pk).update(est_publiee=True)
        Categorie.objects.filter(pk=self.categorie.pk).update(est_active=False)
        self.assertFalse(Session.objects.visibles().exists())


class FicheFormationSessionsTests(PublicMixin, TestCase):
    def test_sessions_ouvertes_affichees_avec_places_et_lien(self):
        reponse = self.client.get(self.formation.get_absolute_url())
        self.assertContains(reponse, 'Prochaines sessions')
        self.assertContains(reponse, 'EXCEL-NOV')
        self.assertContains(reponse, '2 places restantes')
        self.assertContains(reponse, self.url_inscription())

    def test_session_non_publiee_absente(self):
        Session.objects.filter(pk=self.session.pk).update(est_publiee=False)
        reponse = self.client.get(self.formation.get_absolute_url())
        self.assertNotContains(reponse, 'EXCEL-NOV')
        self.assertContains(reponse, 'Aucune session n’est ouverte')

    def test_places_restantes_et_complet(self):
        candidat = Candidat.objects.create(nom='A', prenom='B', telephone='98000001')
        services.confirmer(services.inscrire(candidat, self.session))
        self.assertContains(self.client.get(self.formation.get_absolute_url()), '1 place restante')
        autre = Candidat.objects.create(nom='C', prenom='D', telephone='98000002')
        services.confirmer(services.inscrire(autre, self.session))
        self.assertContains(self.client.get(self.formation.get_absolute_url()), 'Complet — inscription sur liste d’attente')

    def test_bouton_whatsapp_avec_le_code_de_la_session(self):
        ParametresCentre.objects.create(nom='Centre', whatsapp='21612345678')
        reponse = self.client.get(self.formation.get_absolute_url())
        liens = [l for l in reponse.content.decode().split('"') if l.startswith('https://wa.me/21612345678?text=')]
        self.assertTrue(any('EXCEL-NOV' in unquote(lien) for lien in liens))

    def test_aucun_id_numerique_dans_les_liens(self):
        reponse = self.client.get(self.formation.get_absolute_url())
        self.assertNotContains(reponse, f'/sessions/{self.session.pk}/')


class ListeSessionsTests(PublicMixin, TestCase):
    def test_liste_et_menu(self):
        reponse = self.client.get(reverse('enrollments:liste'))
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reverse('enrollments:liste'), '/sessions/')
        self.assertContains(reponse, 'Excel Avancé')
        self.assertContains(reponse, 'EXCEL-NOV')
        self.assertContains(reponse, 'href="/sessions/"')

    def test_liste_vide(self):
        Session.objects.update(est_publiee=False)
        self.assertContains(self.client.get(reverse('enrollments:liste')), 'Aucune session n’est ouverte')


# --- Pré-inscription ------------------------------------------------------------------------

class PageInscriptionTests(PublicMixin, TestCase):
    def test_page_accessible_avec_resume_et_champ_piege(self):
        ParametresCentre.objects.create(nom='Centre', whatsapp='21612345678')
        reponse = self.client.get(self.url_inscription())
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'Salle A')
        self.assertContains(reponse, 'name="site_web"')
        self.assertContains(reponse, 'name="consentement"')
        self.assertIn('EXCEL-NOV', unquote(reponse.context['lien_whatsapp_session']))

    def test_404_si_session_non_visible_ou_inconnue(self):
        Session.objects.filter(pk=self.session.pk).update(statut=Session.Statut.PLANIFIEE)
        self.assertEqual(self.client.get(self.url_inscription()).status_code, 404)
        self.assertEqual(self.client.post(self.url_inscription(), self.donnees()).status_code, 404)
        self.assertEqual(
            self.client.get('/sessions/00000000-0000-0000-0000-000000000000/inscription/').status_code, 404,
        )
        self.assertEqual(self.client.get(f'/sessions/{self.session.pk}/inscription/').status_code, 404)
        self.assertFalse(Candidat.objects.exists())

    def test_nouveau_candidat_et_inscription(self):
        reponse = self.client.post(self.url_inscription(), self.donnees(message='Je préfère le samedi.'), follow=True)
        self.assertRedirects(reponse, reverse('enrollments:merci', kwargs={'uuid': self.session.uuid}))
        self.assertContains(reponse, MESSAGE_SUCCES)
        candidat = Candidat.objects.get()
        self.assertEqual(candidat.telephone, '98123456')  # normalisé
        self.assertEqual(candidat.gouvernorat, 'sfax')
        inscription = Inscription.objects.get()
        self.assertEqual(inscription.candidat, candidat)
        self.assertEqual(inscription.statut, Inscription.Statut.EN_ATTENTE)
        self.assertEqual(inscription.source, Inscription.Source.SITE)
        self.assertEqual(inscription.prix_convenu, Decimal('400.000'))
        self.assertIn('Je préfère le samedi.', inscription.notes)

    def test_candidat_existant_retrouve_par_telephone_sans_modifier_sa_fiche(self):
        existant = Candidat.objects.create(nom='Ben Salah', prenom='Amira', telephone='98123456', email='')
        self.client.post(self.url_inscription(), self.donnees(
            telephone='+216 98-123-456', nom='Autre Nom', email='nouvel@exemple.tn',
        ))
        self.assertEqual(Candidat.objects.count(), 1)
        existant.refresh_from_db()
        self.assertEqual(existant.nom, 'Ben Salah')
        self.assertEqual(existant.email, '')
        notes = Inscription.objects.get(candidat=existant).notes
        self.assertIn('à vérifier', notes)
        self.assertIn('Autre Nom', notes)
        self.assertIn('nouvel@exemple.tn', notes)

    def test_candidat_existant_retrouve_par_email(self):
        existant = Candidat.objects.create(nom='Ben Salah', prenom='Amira', telephone='71000000', email='amira@exemple.tn')
        self.client.post(self.url_inscription(), self.donnees(telephone='22 333 444', email='AMIRA@exemple.tn'))
        self.assertEqual(Candidat.objects.count(), 1)
        self.assertEqual(Inscription.objects.get().candidat, existant)

    def test_cin_prioritaire_sur_le_telephone(self):
        par_cin = Candidat.objects.create(nom='Cin', prenom='A', telephone='71000001', cin='01234567')
        Candidat.objects.create(nom='Tel', prenom='B', telephone='98123456')
        self.client.post(self.url_inscription(), self.donnees(cin='01234567'))
        self.assertEqual(Inscription.objects.get().candidat, par_cin)

    def test_donnees_identiques_pas_de_note(self):
        Candidat.objects.create(nom='Ben Salah', prenom='Amira', telephone='98123456', email='amira@exemple.tn',
                                gouvernorat='sfax')
        self.client.post(self.url_inscription(), self.donnees())
        self.assertEqual(Inscription.objects.get().notes, '')

    def test_deja_inscrit_meme_reponse_sans_doublon(self):
        self.client.post(self.url_inscription(), self.donnees())
        inscription = Inscription.objects.get()
        reponse = self.client.post(self.url_inscription(), self.donnees(message='Encore moi'), follow=True)
        self.assertContains(reponse, MESSAGE_SUCCES)
        self.assertEqual(Inscription.objects.count(), 1)
        inscription.refresh_from_db()
        self.assertNotIn('Encore moi', inscription.notes)

    def test_reinscription_apres_annulation(self):
        self.client.post(self.url_inscription(), self.donnees())
        inscription = services.annuler(Inscription.objects.get())
        self.client.post(self.url_inscription(), self.donnees())
        inscription.refresh_from_db()
        self.assertEqual(inscription.statut, Inscription.Statut.EN_ATTENTE)
        self.assertEqual(Inscription.objects.count(), 1)

    def test_session_complete_inscription_en_liste_d_attente(self):
        for i in range(2):
            candidat = Candidat.objects.create(nom=f'N{i}', prenom='P', telephone=f'9800000{i}')
            services.confirmer(services.inscrire(candidat, self.session))
        self.assertContains(self.client.get(self.url_inscription()), 'liste d’attente')
        self.client.post(self.url_inscription(), self.donnees())
        self.assertEqual(Inscription.objects.filter(statut=Inscription.Statut.EN_ATTENTE).count(), 1)

    def test_champ_piege_rempli_rien_n_est_enregistre(self):
        reponse = self.client.post(self.url_inscription(), self.donnees(site_web='http://spam.example'), follow=True)
        self.assertContains(reponse, MESSAGE_SUCCES)
        self.assertFalse(Candidat.objects.exists())
        self.assertFalse(Inscription.objects.exists())

    def test_validations(self):
        cas = {
            'consentement': {'consentement': ''},
            'telephone': {'telephone': '12'},
            'cin': {'cin': '1234'},
            'nom': {'nom': ''},
            'email': {'email': 'pas-un-email'},
        }
        for champ, valeurs in cas.items():
            with self.subTest(champ=champ):
                reponse = self.client.post(self.url_inscription(), self.donnees(**valeurs))
                self.assertEqual(reponse.status_code, 200)
                self.assertIn(champ, reponse.context['form'].errors)
        self.assertFalse(Candidat.objects.exists())

    def test_email_facultatif(self):
        self.client.post(self.url_inscription(), self.donnees(email=''))
        self.assertTrue(Inscription.objects.exists())

    def test_statut_et_prix_ne_peuvent_pas_etre_forces(self):
        self.client.post(self.url_inscription(), self.donnees(statut='confirmee', prix_convenu='1', source='telephone'))
        inscription = Inscription.objects.get()
        self.assertEqual(inscription.statut, Inscription.Statut.EN_ATTENTE)
        self.assertEqual(inscription.prix_convenu, Decimal('400.000'))
        self.assertEqual(inscription.source, Inscription.Source.SITE)

    def test_refus_du_service_annule_la_creation_du_candidat(self):
        # Si l'inscription est refusée au dernier moment (ex. session fermée entre-temps),
        # le candidat créé dans la même transaction ne doit pas rester en base.
        with mock.patch('enrollments.services.inscrire', side_effect=services.InscriptionImpossible('Session fermée.')):
            reponse = self.client.post(self.url_inscription(), self.donnees())
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'Session fermée.')
        self.assertFalse(Candidat.objects.exists())

    def test_page_merci(self):
        reponse = self.client.get(reverse('enrollments:merci', kwargs={'uuid': self.session.uuid}))
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'EXCEL-NOV')
