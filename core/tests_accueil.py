"""Tests de la page d'accueil : assemblage des blocs fournis par catalog, enrollments et trainers."""

import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Categorie, Formation
from enrollments import services
from enrollments.models import Candidat, Session
from trainers.models import Formateur

from .models import ParametresCentre

URL_ACCUEIL = reverse('core:accueil')
MEDIA_TEST = tempfile.mkdtemp(prefix='media_test_')


def creer_formation(categorie, titre, **champs):
    valeurs = {'resume': f'Résumé {titre}', 'duree_heures': 20, 'prix': Decimal('300'), 'est_publiee': True}
    valeurs.update(champs)
    return Formation.objects.create(categorie=categorie, titre=titre, **valeurs)


class AccueilVideTests(TestCase):
    """Site tout juste installé : la page doit s'afficher proprement, sans chiffre inventé."""

    def test_page_sans_donnees(self):
        reponse = self.client.get(URL_ACCUEIL)
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'Développez vos compétences')
        self.assertContains(reponse, 'Notre catalogue sera bientôt en ligne.')
        self.assertContains(reponse, 'De nouvelles sessions seront bientôt annoncées.')
        self.assertNotContains(reponse, 'class="chiffres-cles"')
        self.assertNotContains(reponse, 'bandeau-defilant')
        self.assertNotContains(reponse, 'Nos formateurs')

    def test_aucun_commentaire_de_gabarit_affiche(self):
        # Un commentaire {# … #} écrit sur plusieurs lignes s'affiche en clair sur la page.
        for url in ('/', '/formations/', '/sessions/', '/a-propos/', '/contact/', '/faq/'):
            with self.subTest(url=url):
                contenu = self.client.get(url).content.decode()
                self.assertNotIn('{#', contenu)
                self.assertNotIn('#}', contenu)

    def test_ressources_statiques_presentes(self):
        self.assertIsNotNone(finders.find('css/site.css'))
        self.assertIsNotNone(finders.find('js/site.js'))
        reponse = self.client.get(URL_ACCUEIL)
        self.assertContains(reponse, 'js/site.js')
        self.assertContains(reponse, 'bootstrap-icons@1.11.3')


class AccueilAvecDonneesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.informatique = Categorie.objects.create(nom='Informatique')
        cls.langues = Categorie.objects.create(nom='Langues')
        cls.inactive = Categorie.objects.create(nom='Domaine Inactif', est_active=False)
        cls.python = creer_formation(cls.informatique, 'Python Débutant')
        cls.excel = creer_formation(cls.informatique, 'Excel Avancé')
        cls.anglais = creer_formation(cls.langues, 'Anglais Professionnel')
        cls.brouillon = creer_formation(cls.informatique, 'Brouillon Caché', est_publiee=False, est_a_la_une=True)
        cls.cachee = creer_formation(cls.inactive, 'Formation Masquée')

    def test_formations_a_la_une_choisies(self):
        Formation.objects.filter(pk=self.excel.pk).update(est_a_la_une=True)
        reponse = self.client.get(URL_ACCUEIL)
        self.assertEqual([f.titre for f in reponse.context['formations']], ['Excel Avancé'])
        self.assertNotContains(reponse, 'Brouillon Caché')  # à la une mais non publiée

    def test_sans_formation_a_la_une_les_dernieres_publiees(self):
        reponse = self.client.get(URL_ACCUEIL)
        titres = {f.titre for f in reponse.context['formations']}
        self.assertEqual(titres, {'Python Débutant', 'Excel Avancé', 'Anglais Professionnel'})

    def test_domaines_visibles_avec_nombre_de_formations(self):
        reponse = self.client.get(URL_ACCUEIL)
        self.assertContains(reponse, 'bandeau-defilant')
        self.assertContains(reponse, '?categorie=informatique')
        self.assertContains(reponse, '2 formations')
        self.assertContains(reponse, '1 formation<')
        self.assertNotContains(reponse, 'Domaine Inactif')

    def test_chiffres_cles_reels_et_chiffres_nuls_masques(self):
        reponse = self.client.get(URL_ACCUEIL)
        self.assertContains(reponse, 'data-compteur="3"')  # 3 formations visibles
        self.assertContains(reponse, 'Formations</p>')
        self.assertNotContains(reponse, 'Sessions ouvertes')
        self.assertNotContains(reponse, 'Stagiaires formés')

    def test_prochaines_sessions_et_stagiaires_formes(self):
        session = Session.objects.create(
            formation=self.python, code='PY-NOV', date_debut=date(2026, 11, 2), date_fin=date(2026, 11, 5),
            places_max=10, statut=Session.Statut.OUVERTE, est_publiee=True,
        )
        Session.objects.create(
            formation=self.excel, code='XL-CACHEE', date_debut=date(2026, 11, 2), date_fin=date(2026, 11, 5),
            places_max=10, statut=Session.Statut.OUVERTE, est_publiee=False,
        )
        candidat = Candidat.objects.create(nom='A', prenom='B', telephone='98000001')
        services.terminer(services.confirmer(services.inscrire(candidat, session)), 'reussi')

        reponse = self.client.get(URL_ACCUEIL)
        self.assertEqual([s.code for s in reponse.context['sessions']], ['PY-NOV'])
        # Agenda compact : ni référence, ni lieu, ni formateur sur la page d'accueil.
        self.assertNotContains(reponse, 'Référence :')
        self.assertNotContains(reponse, 'XL-CACHEE')
        self.assertContains(reponse, reverse('enrollments:inscription', kwargs={'uuid': session.uuid}))
        self.assertContains(reponse, 'Sessions ouvertes')
        self.assertContains(reponse, 'Stagiaires formés')

    def test_formateurs_visibles_sans_donnees_personnelles(self):
        Formateur.objects.create(nom='Trabelsi', prenom='Sami', specialite='Développement web',
                                 est_visible_site=True, email='sami@exemple.tn', telephone='98111222')
        Formateur.objects.create(nom='Discret', prenom='Nadia', est_visible_site=False)
        reponse = self.client.get(URL_ACCUEIL)
        self.assertContains(reponse, 'Nos formateurs')
        self.assertContains(reponse, 'Sami Trabelsi')
        self.assertContains(reponse, 'Développement web')
        self.assertNotContains(reponse, 'Nadia Discret')
        self.assertNotContains(reponse, 'sami@exemple.tn')
        self.assertNotContains(reponse, '98111222')

    def test_cartes_formation_compactes(self):
        # Page d'accueil : durée, modalité et certificat en pastilles, résumé masqué (« Voir plus de détails »),
        # prix sans zéros inutiles.
        Formation.objects.filter(pk=self.python.pk).update(est_certifiante=True)
        reponse = self.client.get(URL_ACCUEIL)
        for contenu in ('20 h', 'bi-building', 'Présentiel', 'bi-patch-check-fill', '300 DT',
                        'Voir plus de détails', 'carte-formation-resume">Résumé Python Débutant'):
            self.assertContains(reponse, contenu)
        self.assertContains(reponse, 'bi-patch-check-fill', count=1)  # seule la formation certifiante
        self.assertNotContains(reponse, '300,000')
        # Le catalogue complet affiche le résumé en entier.
        reponse = self.client.get(reverse('catalog:liste'))
        self.assertContains(reponse, 'Résumé Python Débutant')
        self.assertNotContains(reponse, 'carte-formation-resume')

    def test_bascule_mode_sombre(self):
        reponse = self.client.get(URL_ACCUEIL)
        self.assertContains(reponse, 'data-bs-theme')
        self.assertContains(reponse, 'data-bouton-theme')

    def test_aucun_id_numerique_dans_les_liens(self):
        reponse = self.client.get(URL_ACCUEIL)
        self.assertNotContains(reponse, f'/formations/{self.python.pk}/')


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class AccueilParametresCentreTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEST, ignore_errors=True)

    def test_textes_et_coordonnees_du_centre(self):
        ParametresCentre.objects.create(
            nom='Centre Excellence', slogan='Former pour réussir', telephone='71 000 000',
            whatsapp='21612345678', email='contact@exemple.tn', facebook='https://facebook.com/exemple',
        )
        reponse = self.client.get(URL_ACCUEIL)
        self.assertContains(reponse, 'Former pour réussir')
        self.assertContains(reponse, 'tel:71 000 000')
        self.assertContains(reponse, 'https://wa.me/21612345678')
        self.assertContains(reponse, 'https://facebook.com/exemple')
        self.assertContains(reponse, 'barre-contact')

    # La photo du bandeau est désormais gérée par les emplacements photo (voir tests_photos.py).
