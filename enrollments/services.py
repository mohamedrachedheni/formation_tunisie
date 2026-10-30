"""Règles métier des inscriptions.

Toute création ou tout changement de statut d'une inscription passe par ces fonctions,
qu'il vienne de l'administration ou du site public : les règles sont ainsi appliquées partout.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from commercial.models import DemandeContact
from core.validators import normaliser_telephone

from .models import Candidat, Inscription, Session

# Champs du candidat comparés lors d'une pré-inscription (libellés utilisés dans les notes).
CHAMPS_CANDIDAT_COMPARES = {
    'prenom': 'Prénom', 'nom': 'Nom', 'telephone': 'Téléphone', 'email': 'Email', 'cin': 'CIN',
    'date_naissance': 'Date de naissance', 'gouvernorat': 'Gouvernorat',
    'niveau_etudes': 'Niveau d’études', 'profession': 'Profession',
}


class InscriptionImpossible(ValidationError):
    """Opération refusée par une règle métier (message destiné à l'utilisateur)."""


def verifier_inscription_possible(candidat, session):
    """Vérifie, sans rien enregistrer, qu'une inscription est possible (contrôle préalable des formulaires).

    `inscrire` refait ces contrôles sous verrou au moment de l'enregistrement.
    """
    if not session.accepte_les_inscriptions:
        raise InscriptionImpossible(f'Les inscriptions ne sont pas ouvertes pour cette session ({session.get_statut_display().lower()}).')
    existante = Inscription.objects.filter(candidat=candidat, session=session).exclude(statut=Inscription.Statut.ANNULEE).first()
    if existante:
        raise InscriptionImpossible(f'Ce candidat est déjà inscrit à cette session ({existante.get_statut_display().lower()}).')


def inscrire(candidat, session, source=Inscription.Source.SITE, prix=None, notes=''):
    """Inscrit un candidat à une session (statut « en attente »).

    - La session doit être ouverte aux inscriptions.
    - Le prix est figé maintenant : prix indiqué, sinon prix de la session, sinon prix de la formation.
    - Si le candidat avait une inscription annulée à cette session, elle est réactivée (pas de doublon).
    """
    with transaction.atomic():
        # Verrou sur la session : sérialise les inscriptions concurrentes à une même session.
        session = Session.objects.select_for_update().select_related('formation').get(pk=session.pk)
        if not session.accepte_les_inscriptions:
            raise InscriptionImpossible(f'Les inscriptions ne sont pas ouvertes pour cette session ({session.get_statut_display().lower()}).')

        prix_convenu = session.prix_effectif if prix is None else prix
        existante = Inscription.objects.filter(candidat=candidat, session=session).first()
        if existante is None:
            inscription = Inscription(candidat=candidat, session=session, source=source, prix_convenu=prix_convenu, notes=notes)
            inscription.full_clean()
            inscription.save()
            return inscription

        if existante.statut != Inscription.Statut.ANNULEE:
            raise InscriptionImpossible(f'Ce candidat est déjà inscrit à cette session ({existante.get_statut_display().lower()}).')

        # Réinscription : nouvel engagement, donc nouveau prix et nouvelle source.
        existante.statut = Inscription.Statut.EN_ATTENTE
        existante.prix_convenu = prix_convenu
        existante.source = source
        existante.date_confirmation = None
        if notes:
            existante.notes = f'{existante.notes}\n{notes}'.strip()
        existante.full_clean()
        existante.save()
        return existante


def trouver_candidat(telephone, email='', cin=None):
    """Retrouve un candidat existant, par ordre de fiabilité : CIN, puis téléphone, puis email."""
    if cin:
        candidat = Candidat.objects.filter(cin=cin).first()
        if candidat:
            return candidat
    telephone = normaliser_telephone(telephone)
    if telephone:
        candidat = Candidat.objects.filter(telephone=telephone).order_by('date_creation').first()
        if candidat:
            return candidat
    email = (email or '').strip().lower()
    if email:
        return Candidat.objects.filter(email=email).order_by('date_creation').first()
    return None


def _valeur_comparable(champ, valeur):
    if valeur in (None, ''):
        return ''
    if champ == 'telephone':
        return normaliser_telephone(valeur)
    return str(valeur).strip().casefold()


def _differences(candidat, donnees):
    """Liste lisible des informations saisies qui diffèrent de la fiche existante."""
    lignes = []
    for champ, libelle in CHAMPS_CANDIDAT_COMPARES.items():
        saisie = donnees.get(champ)
        if _valeur_comparable(champ, saisie) and _valeur_comparable(champ, saisie) != _valeur_comparable(champ, getattr(candidat, champ)):
            lignes.append(f'- {libelle} : « {saisie} » (fiche : « {getattr(candidat, champ) or "vide"} »)')
    return lignes


def pre_inscrire(session, donnees_candidat, message=''):
    """Pré-inscription depuis le site public.

    Retourne (inscription, est_nouvelle).
    - Un candidat existant (même CIN, téléphone ou email) est réutilisé ; sa fiche n'est JAMAIS modifiée
      par une saisie publique : les informations différentes sont reportées dans les notes de l'inscription
      pour vérification par le centre.
    - Sinon un candidat est créé.
    - Si le candidat est déjà inscrit (inscription non annulée), rien n'est modifié : est_nouvelle = False.
    - Tout est fait dans une transaction : si l'inscription est refusée, aucun candidat n'est créé.
    """
    with transaction.atomic():
        candidat = trouver_candidat(
            donnees_candidat.get('telephone'), donnees_candidat.get('email'), donnees_candidat.get('cin'),
        )
        notes = []
        if candidat is None:
            candidat = Candidat(**{champ: donnees_candidat.get(champ) for champ in CHAMPS_CANDIDAT_COMPARES if champ in donnees_candidat})
            candidat.full_clean()
            candidat.save()
        else:
            existante = (
                Inscription.objects.filter(candidat=candidat, session=session)
                .exclude(statut=Inscription.Statut.ANNULEE).first()
            )
            if existante:
                return existante, False
            differences = _differences(candidat, donnees_candidat)
            if differences:
                notes.append('Informations saisies sur le site, différentes de la fiche du candidat (à vérifier) :')
                notes.extend(differences)
        if message:
            notes.append(f'Message du candidat : {message}')
        inscription = inscrire(candidat, session, source=Inscription.Source.SITE, notes='\n'.join(notes))
        return inscription, True


class CreationCandidatImpossible(ValidationError):
    """La fiche candidat ne peut pas être créée à partir d'une demande (message destiné au centre)."""


def separer_nom_complet(nom_complet):
    """« Amira Ben Salah » → ('Amira', 'Ben Salah') : le premier mot est pris comme prénom.

    Le visiteur saisit un seul champ « nom et prénom » dans un ordre quelconque :
    le découpage est une proposition que le centre vérifie sur la fiche créée.
    Retourne None si le nom ne contient qu'un mot.
    """
    mots = (nom_complet or '').split()
    if len(mots) < 2:
        return None
    return mots[0], ' '.join(mots[1:])


def candidat_depuis_demande(demande, utilisateur):
    """Crée (ou retrouve) la fiche candidat d'une demande de contact.

    Retourne (candidat, est_nouveau).
    - Un candidat existant (même téléphone ou même email) est réutilisé et sa fiche n'est pas modifiée :
      les coordonnées différentes sont reportées dans les notes internes de la demande.
    - Sinon une fiche est créée avec le prénom, le nom, le téléphone et l'email de la demande.
      Le téléphone est obligatoire pour un candidat : une demande sans téléphone est refusée.
    - La demande passe de « Nouvelle » à « En cours » (une demande déjà traitée garde son statut),
      le responsable est renseigné s'il est vide, et l'opération est tracée dans les notes internes.
    """
    with transaction.atomic():
        # Verrou sur la demande : un double clic ne crée pas deux fiches.
        demande = DemandeContact.objects.select_for_update().get(pk=demande.pk)
        candidat = trouver_candidat(demande.telephone, demande.email)
        est_nouveau = candidat is None
        if est_nouveau:
            if not demande.telephone:
                raise CreationCandidatImpossible(
                    'la demande n’a pas de téléphone, obligatoire pour une fiche candidat : '
                    'créez la fiche manuellement après avoir obtenu le numéro.'
                )
            noms = separer_nom_complet(demande.nom)
            if noms is None:
                raise CreationCandidatImpossible(
                    'le nom ne contient qu’un mot (prénom et nom requis) : créez la fiche manuellement.'
                )
            candidat = Candidat(prenom=noms[0], nom=noms[1], telephone=demande.telephone, email=demande.email)
            candidat.full_clean()
            candidat.save()
            notes = [f'Fiche candidat créée : {candidat}.']
        else:
            notes = [f'Candidat existant retrouvé : {candidat} (aucune fiche créée).']
            differences = _differences(candidat, {'telephone': demande.telephone, 'email': demande.email})
            if differences:
                notes.append('Coordonnées de la demande différentes de la fiche (à vérifier) :')
                notes.extend(differences)

        horodatage = timezone.localtime().strftime('%d/%m/%Y %H:%M')
        notes[0] = f'[{horodatage}] {notes[0]}'
        demande.notes = '\n'.join(filter(None, [demande.notes.strip(), *notes]))
        if demande.statut == DemandeContact.Statut.NOUVELLE:
            demande.statut = DemandeContact.Statut.EN_COURS
        if demande.traitee_par_id is None:
            demande.traitee_par = utilisateur
        demande.save(update_fields=['notes', 'statut', 'traitee_par', 'date_modification'])
        return candidat, est_nouveau


def confirmer(inscription):
    """Confirme une inscription en attente si une place est disponible."""
    with transaction.atomic():
        # Verrou sur la session puis relecture : deux confirmations simultanées
        # ne peuvent pas attribuer la dernière place deux fois.
        session = Session.objects.select_for_update().get(pk=inscription.session_id)
        inscription = Inscription.objects.select_for_update().get(pk=inscription.pk)
        if inscription.statut != Inscription.Statut.EN_ATTENTE:
            raise InscriptionImpossible(f'Seule une inscription en attente peut être confirmée ({inscription.get_statut_display().lower()}).')
        if session.statut not in (Session.Statut.OUVERTE, Session.Statut.EN_COURS):
            raise InscriptionImpossible(f'La session n’accepte plus de confirmation ({session.get_statut_display().lower()}).')
        if session.places_occupees >= session.places_max:
            raise InscriptionImpossible(f'La session est complète ({session.places_max} place(s)).')

        inscription.statut = Inscription.Statut.CONFIRMEE
        inscription.date_confirmation = timezone.now()
        inscription.save(update_fields=['statut', 'date_confirmation', 'date_modification'])
        return inscription


def annuler(inscription):
    """Annule une inscription en attente ou confirmée (la place éventuelle est libérée)."""
    with transaction.atomic():
        inscription = Inscription.objects.select_for_update().get(pk=inscription.pk)
        if inscription.statut not in (Inscription.Statut.EN_ATTENTE, Inscription.Statut.CONFIRMEE):
            raise InscriptionImpossible(f'Cette inscription ne peut pas être annulée ({inscription.get_statut_display().lower()}).')
        inscription.statut = Inscription.Statut.ANNULEE
        inscription.save(update_fields=['statut', 'date_modification'])
        return inscription


def terminer(inscription, resultat):
    """Clôture une inscription confirmée avec son résultat (réussi ou échoué)."""
    if resultat not in Inscription.Resultat.values:
        raise InscriptionImpossible('Résultat invalide.')
    with transaction.atomic():
        inscription = Inscription.objects.select_for_update().get(pk=inscription.pk)
        if inscription.statut != Inscription.Statut.CONFIRMEE:
            raise InscriptionImpossible(f'Seule une inscription confirmée peut être clôturée ({inscription.get_statut_display().lower()}).')
        inscription.statut = Inscription.Statut.TERMINEE
        inscription.resultat = resultat
        inscription.save(update_fields=['statut', 'resultat', 'date_modification'])
        return inscription
