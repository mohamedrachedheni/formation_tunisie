"""Règles métier des certificats.

Toute délivrance, correction ou annulation passe par ces fonctions : un certificat n'est jamais
créé, modifié ou supprimé directement depuis l'administration.
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.models import ParametresCentre
from enrollments.models import Inscription

from .models import Certificat

# Résultat de l'inscription → document délivré.
TYPE_PAR_RESULTAT = {
    Inscription.Resultat.REUSSI: Certificat.Type.REUSSITE,
    Inscription.Resultat.ECHOUE: Certificat.Type.PARTICIPATION,
}
ESSAIS_NUMERO = 5


class CertificatImpossible(ValidationError):
    """Opération refusée par une règle métier (message destiné au centre)."""


def _verifier_inscription(inscription):
    if inscription.statut != Inscription.Statut.TERMINEE or inscription.resultat not in TYPE_PAR_RESULTAT:
        raise CertificatImpossible(
            'Seule une inscription terminée (avec un résultat) donne droit à un document '
            f'({inscription.get_statut_display().lower()}).'
        )


def _contenu(inscription):
    """Contenu imprimé sur le document, recopié depuis l'inscription et les paramètres du centre."""
    session = inscription.session
    parametres = ParametresCentre.obtenir()
    return {
        'type': TYPE_PAR_RESULTAT[inscription.resultat],
        'titulaire': inscription.candidat.nom_complet,
        'formation_titre': session.formation.titre,
        'duree_heures': session.formation.duree_heures,
        'date_debut': session.date_debut,
        'date_fin': session.date_fin,
        'signataire_nom': parametres.signataire_nom if parametres else '',
        'signataire_fonction': parametres.signataire_fonction if parametres else '',
    }


def _prochain_numero(annee):
    """Numéro suivant de l'année : CERT-AAAA-00001, CERT-AAAA-00002…

    Lecture verrouillante (select_for_update) : elle voit les derniers numéros enregistrés
    et sérialise les délivrances simultanées. Un conflit restant est rattrapé par un nouvel essai.
    """
    prefixe = f'{Certificat.PREFIXE_NUMERO}-{annee}-'
    dernier = (
        Certificat.objects.select_for_update().filter(numero__startswith=prefixe)
        .order_by('-numero').values_list('numero', flat=True).first()
    )
    rang = int(dernier.rsplit('-', 1)[1]) + 1 if dernier else 1
    return f'{prefixe}{rang:05d}'


def delivrer(inscription, utilisateur):
    """Délivre le document d'une inscription terminée.

    Retourne (certificat, est_nouveau).
    - Résultat « réussi » → certificat de réussite ; « échoué » → attestation de participation.
    - Un seul document par inscription : si un certificat valide existe, la délivrance est refusée ;
      un certificat annulé est remis en vigueur avec le même numéro (jamais de doublon).
    """
    with transaction.atomic():
        inscription = (
            Inscription.objects.select_for_update()
            .select_related('candidat', 'session__formation').get(pk=inscription.pk)
        )
        _verifier_inscription(inscription)
        aujourd_hui = timezone.localdate()
        existant = Certificat.objects.select_for_update().filter(inscription=inscription).first()
        if existant and existant.est_valide:
            raise CertificatImpossible(f'Un document a déjà été délivré pour cette inscription ({existant.numero}).')

        if existant:
            for champ, valeur in _contenu(inscription).items():
                setattr(existant, champ, valeur)
            existant.statut = Certificat.Statut.VALIDE
            existant.motif_annulation = ''
            existant.date_annulation = None
            existant.date_delivrance = aujourd_hui
            existant.delivre_par = utilisateur
            existant.full_clean()
            existant.save()
            return existant, False

        for _ in range(ESSAIS_NUMERO):
            certificat = Certificat(
                inscription=inscription, numero=_prochain_numero(aujourd_hui.year),
                date_delivrance=aujourd_hui, delivre_par=utilisateur, **_contenu(inscription),
            )
            # L'unicité du numéro est vérifiée par la base (et non par full_clean) : en cas de délivrance
            # simultanée, l'enregistrement échoue et un nouveau numéro est calculé.
            certificat.full_clean(validate_unique=False)
            try:
                with transaction.atomic():
                    certificat.save()
                return certificat, True
            except IntegrityError:
                if Certificat.objects.filter(inscription=inscription).exists():
                    raise CertificatImpossible('Un document a déjà été délivré pour cette inscription.')
        raise CertificatImpossible('Numéro de certificat indisponible, réessayez.')


def mettre_a_jour(certificat):
    """Corrige un certificat valide à partir de l'inscription et des paramètres actuels
    (nom du candidat corrigé, intitulé de formation, signataire…).

    Le numéro et la date de délivrance ne changent pas.
    """
    with transaction.atomic():
        certificat = Certificat.objects.select_for_update().get(pk=certificat.pk)
        if not certificat.est_valide:
            raise CertificatImpossible(f'Un certificat annulé ne peut pas être mis à jour ({certificat.numero}).')
        inscription = Inscription.objects.select_related('candidat', 'session__formation').get(pk=certificat.inscription_id)
        _verifier_inscription(inscription)
        for champ, valeur in _contenu(inscription).items():
            setattr(certificat, champ, valeur)
        certificat.full_clean()
        certificat.save()
        return certificat


def annuler(certificat, motif):
    """Annule un certificat valide. Il est conservé : la page de vérification indique « annulé »."""
    motif = (motif or '').strip()
    if not motif:
        raise CertificatImpossible('Le motif d’annulation est obligatoire.')
    with transaction.atomic():
        certificat = Certificat.objects.select_for_update().get(pk=certificat.pk)
        if not certificat.est_valide:
            raise CertificatImpossible(f'Ce certificat est déjà annulé ({certificat.numero}).')
        certificat.statut = Certificat.Statut.ANNULE
        certificat.motif_annulation = motif
        certificat.date_annulation = timezone.now()
        certificat.full_clean()
        certificat.save()
        return certificat
