import threading
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Roles
from catalog.models import Categorie, Formation
from trainers.models import Formateur

from . import services
from .models import Candidat, Inscription, Session
from .services import InscriptionImpossible

Utilisateur = get_user_model()


class DonneesMixin:
    @classmethod
    def setUpTestData(cls):
        categorie = Categorie.objects.create(nom='Bureautique')
        cls.formation = Formation.objects.create(
            categorie=categorie, titre='Excel Avancé', resume='r', duree_heures=20, prix=Decimal('400.000'),
        )
        cls.formateur = Formateur.objects.create(nom='Trabelsi', prenom='Sami')

    def creer_session(self, **champs):
        valeurs = {'formation': self.formation, 'date_debut': date(2026, 11, 2), 'date_fin': date(2026, 11, 20),
                   'places_max': 2, 'statut': Session.Statut.OUVERTE}
        valeurs.update(champs)
        return Session.objects.create(**valeurs)

    def creer_candidat(self, nom='Ben Salah', telephone='98123456', **champs):
        return Candidat.objects.create(nom=nom, prenom='Amira', telephone=telephone, **champs)


# --- Session --------------------------------------------------------------------------------

class SessionModeleTests(DonneesMixin, TestCase):
    def test_code_et_modalite_par_defaut(self):
        session = self.creer_session()
        self.assertEqual(session.code, 'EXCEL-AVANCE-2026-11')
        self.assertEqual(session.modalite, self.formation.modalite)

    def test_code_genere_unique(self):
        premiere = self.creer_session()
        seconde = self.creer_session(date_debut=date(2026, 11, 15))
        self.assertNotEqual(premiere.code, seconde.code)
        self.assertEqual(seconde.code, 'EXCEL-AVANCE-2026-11-2')

    def test_code_saisi_unique_en_base(self):
        self.creer_session(code='EXC-01')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.creer_session(code='EXC-01')

    def test_prix_effectif(self):
        self.assertEqual(self.creer_session().prix_effectif, Decimal('400.000'))
        self.assertEqual(self.creer_session(prix=Decimal('350.500')).prix_effectif, Decimal('350.500'))

    def test_contraintes_en_base(self):
        cas = {
            'date de fin avant le début': {'date_debut': date(2026, 11, 20), 'date_fin': date(2026, 11, 2)},
            'zéro place': {'places_max': 0},
            'prix négatif': {'prix': Decimal('-1')},
        }
        for libelle, champs in cas.items():
            with self.subTest(libelle), self.assertRaises(IntegrityError), transaction.atomic():
                self.creer_session(code=f'X-{len(libelle)}', **champs)

    def test_meme_jour_autorise(self):
        session = self.creer_session(date_debut=date(2026, 11, 2), date_fin=date(2026, 11, 2))
        self.assertEqual(session.date_debut, session.date_fin)

    def test_validation_dates(self):
        session = Session(formation=self.formation, date_debut=date(2026, 11, 20), date_fin=date(2026, 11, 2), places_max=5)
        with self.assertRaises(ValidationError) as erreur:
            session.full_clean()
        self.assertIn('date_fin', erreur.exception.message_dict)

    def test_formateur_inactif_refuse_a_l_affectation(self):
        inactif = Formateur.objects.create(nom='Inactif', prenom='X', est_actif=False)
        with self.assertRaises(ValidationError) as erreur:
            Session(formation=self.formation, formateur=inactif, date_debut=date(2026, 11, 2),
                    date_fin=date(2026, 11, 3), places_max=5).full_clean()
        self.assertIn('formateur', erreur.exception.message_dict)

    def test_formateur_desactive_apres_affectation_reste_accepte(self):
        session = self.creer_session(formateur=self.formateur)
        Formateur.objects.filter(pk=self.formateur.pk).update(est_actif=False)
        session.refresh_from_db()
        session.lieu = 'Salle 2'
        session.full_clean()

    def test_places_max_pas_en_dessous_des_places_occupees(self):
        session = self.creer_session(places_max=2)
        for telephone in ('98000001', '98000002'):
            services.confirmer(services.inscrire(self.creer_candidat(telephone=telephone), session))
        session.places_max = 1
        with self.assertRaises(ValidationError) as erreur:
            session.full_clean()
        self.assertIn('places_max', erreur.exception.message_dict)

    def test_suppressions_protegees(self):
        session = self.creer_session(formateur=self.formateur)
        services.inscrire(self.creer_candidat(), session)
        for objet in (self.formation, self.formateur, session):
            with self.subTest(objet=type(objet).__name__), self.assertRaises(ProtectedError):
                objet.delete()

    def test_places_occupees_et_annotation(self):
        session = self.creer_session(places_max=3)
        confirmee = services.inscrire(self.creer_candidat(telephone='98000001'), session)
        services.confirmer(confirmee)
        services.inscrire(self.creer_candidat(telephone='98000002'), session)  # en attente : n'occupe pas de place
        annulee = services.inscrire(self.creer_candidat(telephone='98000003'), session)
        services.annuler(annulee)
        self.assertEqual(session.places_occupees, 1)
        self.assertEqual(session.places_restantes, 2)
        self.assertEqual(Session.objects.avec_places_occupees().get(pk=session.pk).places_occupees, 1)


# --- Candidat -------------------------------------------------------------------------------

class CandidatModeleTests(DonneesMixin, TestCase):
    def test_creation_et_normalisation(self):
        candidat = self.creer_candidat(email=' Amira@Exemple.TN ', cin='')
        candidat.refresh_from_db()
        self.assertEqual(candidat.email, 'amira@exemple.tn')
        self.assertIsNone(candidat.cin)
        self.assertEqual(str(candidat), 'Amira Ben Salah (98123456)')

    def test_plusieurs_candidats_sans_cin(self):
        self.creer_candidat(telephone='98000001')
        self.creer_candidat(telephone='98000002')
        self.assertEqual(Candidat.objects.filter(cin__isnull=True).count(), 2)

    def test_cin_unique(self):
        self.creer_candidat(cin='01234567')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.creer_candidat(telephone='98000002', cin='01234567')

    def test_format_cin_refuse_par_la_base(self):
        for cin in ('1234567', 'ABCDEFGH', '1234567X'):
            with self.subTest(cin=cin), self.assertRaises(IntegrityError), transaction.atomic():
                self.creer_candidat(cin=cin)

    def test_format_cin_et_telephone_valides_par_le_formulaire(self):
        with self.assertRaises(ValidationError) as erreur:
            Candidat(nom='A', prenom='B', telephone='12', cin='123').full_clean()
        self.assertIn('cin', erreur.exception.message_dict)
        self.assertIn('telephone', erreur.exception.message_dict)

    def test_telephone_obligatoire(self):
        with self.assertRaises(ValidationError) as erreur:
            Candidat(nom='A', prenom='B').full_clean()
        self.assertIn('telephone', erreur.exception.message_dict)

    def test_suppression_du_compte_conserve_le_candidat(self):
        compte = Utilisateur.objects.create_user(username='amira', email='amira@exemple.tn', password='x')
        candidat = self.creer_candidat(utilisateur=compte)
        compte.delete()
        candidat.refresh_from_db()
        self.assertIsNone(candidat.utilisateur)


# --- Inscription : contraintes --------------------------------------------------------------

class InscriptionContraintesTests(DonneesMixin, TestCase):
    def setUp(self):
        self.session = self.creer_session()
        self.candidat = self.creer_candidat()

    def creer(self, **champs):
        valeurs = {'candidat': self.candidat, 'session': self.session, 'prix_convenu': Decimal('400')}
        valeurs.update(champs)
        return Inscription.objects.create(**valeurs)

    def test_une_seule_inscription_par_candidat_et_session(self):
        self.creer()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.creer()

    def test_contraintes_en_base(self):
        cas = {
            'prix négatif': {'prix_convenu': Decimal('-1')},
            'résultat sans clôture': {'resultat': Inscription.Resultat.REUSSI},
            'confirmée sans date': {'statut': Inscription.Statut.CONFIRMEE},
        }
        for libelle, champs in cas.items():
            with self.subTest(libelle), self.assertRaises(IntegrityError), transaction.atomic():
                self.creer(**champs)

    def test_terminee_avec_resultat_et_date_acceptee(self):
        inscription = self.creer(statut=Inscription.Statut.TERMINEE, resultat=Inscription.Resultat.REUSSI,
                                 date_confirmation=timezone.now())
        self.assertTrue(inscription.occupe_une_place)

    def test_candidat_avec_inscriptions_protege(self):
        self.creer()
        with self.assertRaises(ProtectedError):
            self.candidat.delete()


# --- Services -------------------------------------------------------------------------------

class ServicesInscriptionTests(DonneesMixin, TestCase):
    def setUp(self):
        self.session = self.creer_session(places_max=1)
        self.candidat = self.creer_candidat()

    def test_inscrire_fige_le_prix_de_la_formation(self):
        inscription = services.inscrire(self.candidat, self.session, source=Inscription.Source.WHATSAPP)
        self.assertEqual(inscription.statut, Inscription.Statut.EN_ATTENTE)
        self.assertEqual(inscription.prix_convenu, Decimal('400.000'))
        self.assertEqual(inscription.source, Inscription.Source.WHATSAPP)
        # Un changement de tarif ultérieur ne modifie pas le prix convenu.
        Formation.objects.filter(pk=self.formation.pk).update(prix=Decimal('999'))
        inscription.refresh_from_db()
        self.assertEqual(inscription.prix_convenu, Decimal('400.000'))

    def test_inscrire_prix_de_session_ou_prix_negocie(self):
        session = self.creer_session(code='PROMO', prix=Decimal('300.000'))
        self.assertEqual(services.inscrire(self.candidat, session).prix_convenu, Decimal('300.000'))
        autre = self.creer_candidat(telephone='98000002')
        self.assertEqual(services.inscrire(autre, session, prix=Decimal('250')).prix_convenu, Decimal('250.000'))

    def test_inscription_refusee_si_session_non_ouverte(self):
        for statut in (Session.Statut.PLANIFIEE, Session.Statut.EN_COURS, Session.Statut.TERMINEE, Session.Statut.ANNULEE):
            Session.objects.filter(pk=self.session.pk).update(statut=statut)
            with self.subTest(statut=statut), self.assertRaises(InscriptionImpossible):
                services.inscrire(self.candidat, self.session)
        self.assertFalse(Inscription.objects.exists())

    def test_double_inscription_refusee(self):
        services.inscrire(self.candidat, self.session)
        with self.assertRaises(InscriptionImpossible):
            services.inscrire(self.candidat, self.session)
        self.assertEqual(Inscription.objects.count(), 1)

    def test_reinscription_apres_annulation_reactive_la_meme_ligne(self):
        inscription = services.inscrire(self.candidat, self.session)
        services.annuler(inscription)
        Formation.objects.filter(pk=self.formation.pk).update(prix=Decimal('450'))
        reactivee = services.inscrire(self.candidat, self.session, source=Inscription.Source.TELEPHONE)
        self.assertEqual(reactivee.pk, inscription.pk)
        self.assertEqual(reactivee.statut, Inscription.Statut.EN_ATTENTE)
        self.assertEqual(reactivee.prix_convenu, Decimal('450'))
        self.assertEqual(Inscription.objects.count(), 1)

    def test_confirmer_dans_la_limite_des_places(self):
        premiere = services.inscrire(self.candidat, self.session)
        seconde = services.inscrire(self.creer_candidat(telephone='98000002'), self.session)
        services.confirmer(premiere)
        premiere.refresh_from_db()
        self.assertEqual(premiere.statut, Inscription.Statut.CONFIRMEE)
        self.assertIsNotNone(premiere.date_confirmation)
        with self.assertRaisesMessage(InscriptionImpossible, 'complète'):
            services.confirmer(seconde)
        seconde.refresh_from_db()
        self.assertEqual(seconde.statut, Inscription.Statut.EN_ATTENTE)

    def test_annulation_libere_la_place(self):
        premiere = services.confirmer(services.inscrire(self.candidat, self.session))
        seconde = services.inscrire(self.creer_candidat(telephone='98000002'), self.session)
        services.annuler(premiere)
        self.assertEqual(services.confirmer(seconde).statut, Inscription.Statut.CONFIRMEE)

    def test_confirmation_possible_session_en_cours_mais_pas_annulee(self):
        inscription = services.inscrire(self.candidat, self.session)
        Session.objects.filter(pk=self.session.pk).update(statut=Session.Statut.EN_COURS)
        services.confirmer(inscription)
        autre_session = self.creer_session(code='AUTRE')
        autre = services.inscrire(self.candidat, autre_session)
        Session.objects.filter(pk=autre_session.pk).update(statut=Session.Statut.ANNULEE)
        with self.assertRaises(InscriptionImpossible):
            services.confirmer(autre)

    def test_transitions_interdites(self):
        inscription = services.inscrire(self.candidat, self.session)
        with self.assertRaises(InscriptionImpossible):
            services.terminer(inscription, Inscription.Resultat.REUSSI)  # pas encore confirmée
        services.confirmer(inscription)
        with self.assertRaises(InscriptionImpossible):
            services.confirmer(inscription)  # déjà confirmée
        services.terminer(inscription, Inscription.Resultat.ECHOUE)
        with self.assertRaises(InscriptionImpossible):
            services.annuler(inscription)  # terminée
        inscription.refresh_from_db()
        self.assertEqual(inscription.statut, Inscription.Statut.TERMINEE)
        self.assertEqual(inscription.resultat, Inscription.Resultat.ECHOUE)

    def test_resultat_invalide(self):
        inscription = services.confirmer(services.inscrire(self.candidat, self.session))
        with self.assertRaises(InscriptionImpossible):
            services.terminer(inscription, 'excellent')

    def test_verifier_inscription_possible(self):
        services.verifier_inscription_possible(self.candidat, self.session)
        inscription = services.inscrire(self.candidat, self.session)
        with self.assertRaises(InscriptionImpossible):
            services.verifier_inscription_possible(self.candidat, self.session)
        services.annuler(inscription)
        services.verifier_inscription_possible(self.candidat, self.session)  # réinscription possible


class ConcurrenceConfirmationTests(DonneesMixin, TransactionTestCase):
    """Deux confirmations simultanées pour la dernière place : une seule doit réussir."""

    # Restaure les données créées par les migrations (groupes, permissions) après le test.
    serialized_rollback = True

    def setUp(self):
        categorie = Categorie.objects.create(nom='Bureautique')
        self.formation = Formation.objects.create(
            categorie=categorie, titre='Excel Avancé', resume='r', duree_heures=20, prix=Decimal('400.000'),
        )

    @classmethod
    def setUpTestData(cls):
        pass  # Non utilisé par TransactionTestCase : les données sont créées dans setUp.

    def test_derniere_place_attribuee_une_seule_fois(self):
        session = self.creer_session(places_max=1)
        inscriptions = [services.inscrire(self.creer_candidat(telephone=f'9800000{i}'), session) for i in range(2)]
        depart = threading.Barrier(2)
        resultats = []

        def confirmer_en_parallele(inscription):
            try:
                depart.wait()
                services.confirmer(inscription)
                resultats.append('confirmée')
            except InscriptionImpossible:
                resultats.append('refusée')
            finally:
                connection.close()  # chaque thread a sa propre connexion à la base

        threads = [threading.Thread(target=confirmer_en_parallele, args=(i,)) for i in inscriptions]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(sorted(resultats), ['confirmée', 'refusée'])
        self.assertEqual(Inscription.objects.filter(statut=Inscription.Statut.CONFIRMEE).count(), 1)


# --- Permissions et administration ----------------------------------------------------------

class PermissionsEnrollmentsTests(TestCase):
    def test_droits_des_groupes(self):
        gestionnaire = set(Group.objects.get(name=Roles.GESTIONNAIRE).permissions.values_list('codename', flat=True))
        administrateur = set(Group.objects.get(name=Roles.ADMINISTRATEUR).permissions.values_list('codename', flat=True))
        for modele in ('session', 'candidat', 'inscription'):
            with self.subTest(modele=modele):
                self.assertTrue({f'view_{modele}', f'add_{modele}', f'change_{modele}'} <= gestionnaire)
                self.assertNotIn(f'delete_{modele}', gestionnaire)
                self.assertIn(f'delete_{modele}', administrateur)
        self.assertIn('valider_inscription', gestionnaire)
        self.assertIn('valider_inscription', administrateur)
        for role in (Roles.FORMATEUR, Roles.CANDIDAT):
            with self.subTest(role=role):
                self.assertFalse(Group.objects.get(name=role).permissions.filter(content_type__app_label='enrollments').exists())


class AdministrationEnrollmentsTests(DonneesMixin, TestCase):
    def setUp(self):
        self.gestionnaire = Utilisateur.objects.create_user(username='gest', email='gest@exemple.tn', password='x', is_staff=True)
        self.gestionnaire.groups.add(Group.objects.get(name=Roles.GESTIONNAIRE))
        self.client.force_login(self.gestionnaire)
        self.session = self.creer_session(places_max=1)
        self.candidat = self.creer_candidat()

    def action(self, nom, *inscriptions):
        return self.client.post(reverse('admin:enrollments_inscription_changelist'), {
            'action': nom, '_selected_action': [i.pk for i in inscriptions],
        }, follow=True)

    def test_pages_admin(self):
        inscription = services.inscrire(self.candidat, self.session)
        for url in (
            reverse('admin:enrollments_session_changelist'),
            reverse('admin:enrollments_session_add'),
            reverse('admin:enrollments_session_change', args=[self.session.pk]),
            reverse('admin:enrollments_candidat_changelist'),
            reverse('admin:enrollments_candidat_change', args=[self.candidat.pk]),
            reverse('admin:enrollments_inscription_changelist'),
            reverse('admin:enrollments_inscription_add'),
            reverse('admin:enrollments_inscription_change', args=[inscription.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_navigation_par_date_des_sessions(self):
        # date_hierarchy sur un DateField : ne dépend pas des tables de fuseaux horaires de MariaDB.
        reponse = self.client.get(reverse('admin:enrollments_session_changelist'), {'date_debut__year': 2026})
        self.assertEqual(reponse.status_code, 200)

    def test_ajout_inscription_passe_par_le_service(self):
        reponse = self.client.post(reverse('admin:enrollments_inscription_add'), {
            'candidat': self.candidat.pk, 'session': self.session.pk, 'source': 'telephone', 'prix_convenu': '', 'notes': '',
        })
        self.assertEqual(reponse.status_code, 302)
        inscription = Inscription.objects.get()
        self.assertEqual(inscription.prix_convenu, Decimal('400.000'))
        self.assertEqual(inscription.statut, Inscription.Statut.EN_ATTENTE)

    def test_ajout_refuse_si_session_non_ouverte(self):
        Session.objects.filter(pk=self.session.pk).update(statut=Session.Statut.PLANIFIEE)
        reponse = self.client.post(reverse('admin:enrollments_inscription_add'), {
            'candidat': self.candidat.pk, 'session': self.session.pk, 'source': 'telephone', 'prix_convenu': '', 'notes': '',
        })
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'Les inscriptions ne sont pas ouvertes')
        self.assertFalse(Inscription.objects.exists())

    def test_ajout_refuse_si_deja_inscrit(self):
        services.inscrire(self.candidat, self.session)
        reponse = self.client.post(reverse('admin:enrollments_inscription_add'), {
            'candidat': self.candidat.pk, 'session': self.session.pk, 'source': 'telephone', 'prix_convenu': '', 'notes': '',
        })
        self.assertContains(reponse, 'déjà inscrit')
        self.assertEqual(Inscription.objects.count(), 1)

    def test_ajout_reactive_une_inscription_annulee(self):
        inscription = services.annuler(services.inscrire(self.candidat, self.session))
        reponse = self.client.post(reverse('admin:enrollments_inscription_add'), {
            'candidat': self.candidat.pk, 'session': self.session.pk, 'source': 'sur_place', 'prix_convenu': '380', 'notes': '',
        })
        self.assertEqual(reponse.status_code, 302)
        inscription.refresh_from_db()
        self.assertEqual(inscription.statut, Inscription.Statut.EN_ATTENTE)
        self.assertEqual(inscription.prix_convenu, Decimal('380'))
        self.assertEqual(Inscription.objects.count(), 1)

    def test_statut_et_prix_non_modifiables_dans_le_formulaire(self):
        inscription = services.inscrire(self.candidat, self.session)
        self.client.post(reverse('admin:enrollments_inscription_change', args=[inscription.pk]), {
            'statut': 'confirmee', 'prix_convenu': '1', 'notes': 'Paiera en deux fois',
        })
        inscription.refresh_from_db()
        self.assertEqual(inscription.statut, Inscription.Statut.EN_ATTENTE)
        self.assertEqual(inscription.prix_convenu, Decimal('400.000'))
        self.assertEqual(inscription.notes, 'Paiera en deux fois')

    def test_action_confirmer_respecte_les_places(self):
        premiere = services.inscrire(self.candidat, self.session)
        seconde = services.inscrire(self.creer_candidat(telephone='98000002'), self.session)
        reponse = self.action('confirmer', premiere, seconde)
        premiere.refresh_from_db()
        seconde.refresh_from_db()
        # La plus ancienne demande est confirmée en premier ; la seconde est refusée (session complète).
        self.assertEqual(premiere.statut, Inscription.Statut.CONFIRMEE)
        self.assertEqual(seconde.statut, Inscription.Statut.EN_ATTENTE)
        self.assertContains(reponse, '1 inscription(s) confirmée(s).')
        self.assertContains(reponse, 'complète')

    def test_actions_cloturer_et_remettre_en_attente(self):
        inscription = services.confirmer(services.inscrire(self.candidat, self.session))
        self.action('terminer_reussi', inscription)
        inscription.refresh_from_db()
        self.assertEqual((inscription.statut, inscription.resultat), (Inscription.Statut.TERMINEE, Inscription.Resultat.REUSSI))

        autre = services.annuler(services.inscrire(self.creer_candidat(telephone='98000002'), self.creer_session(code='B')))
        self.action('remettre_en_attente', autre)
        autre.refresh_from_db()
        self.assertEqual(autre.statut, Inscription.Statut.EN_ATTENTE)

    def test_gestionnaire_sans_suppression(self):
        inscription = services.inscrire(self.candidat, self.session)
        for url in (
            reverse('admin:enrollments_session_delete', args=[self.session.pk]),
            reverse('admin:enrollments_candidat_delete', args=[self.candidat.pk]),
            reverse('admin:enrollments_inscription_delete', args=[inscription.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_actions_de_statut_reservees_a_valider_inscription(self):
        sans_droit = Utilisateur.objects.create_user(username='lecteur', email='lecteur@exemple.tn', password='x', is_staff=True)
        from django.contrib.auth.models import Permission
        sans_droit.user_permissions.add(*Permission.objects.filter(codename__in=['view_inscription', 'change_inscription']))
        self.client.force_login(sans_droit)
        reponse = self.client.get(reverse('admin:enrollments_inscription_changelist'))
        self.assertEqual(reponse.status_code, 200)
        # Sans action autorisée, Django n'affiche pas le menu des actions (action_form vaut None).
        action_form = reponse.context['action_form']
        actions = [nom for nom, _ in action_form.fields['action'].choices] if action_form else []
        self.assertNotIn('confirmer', actions)
        self.assertNotIn('annuler', actions)

    def test_formateur_sans_acces(self):
        formateur = Utilisateur.objects.create_user(username='form', email='form@exemple.tn', password='x', is_staff=True)
        formateur.groups.add(Group.objects.get(name=Roles.FORMATEUR))
        self.client.force_login(formateur)
        self.assertEqual(self.client.get(reverse('admin:enrollments_inscription_changelist')).status_code, 403)
