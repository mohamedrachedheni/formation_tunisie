"""Règles d'accès aux espaces personnels et aux documents réservés.

Un accès suppose toujours DEUX conditions : le rôle (groupe Django) ET le rattachement du compte
à une fiche (Candidat ou Formateur). Chaque vue vérifie en plus que l'objet consulté appartient
bien à la personne connectée (sa propre inscription, sa propre session).
"""

from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied

from accounts.models import Roles
from catalog.models import Formation
from enrollments.models import Inscription, Session


def candidat_de(utilisateur):
    """Fiche candidat du compte, si le compte a le rôle Candidat ; sinon None."""
    if not utilisateur.is_authenticated or not utilisateur.a_le_role(Roles.CANDIDAT):
        return None
    try:
        return utilisateur.candidat
    except ObjectDoesNotExist:
        return None


def formateur_de(utilisateur):
    """Fiche formateur ACTIVE du compte, si le compte a le rôle Formateur ; sinon None."""
    if not utilisateur.is_authenticated or not utilisateur.a_le_role(Roles.FORMATEUR):
        return None
    try:
        formateur = utilisateur.formateur
    except ObjectDoesNotExist:
        return None
    # Un formateur désactivé n'accède plus à son espace.
    return formateur if formateur.est_actif else None


class EspaceCandidatMixin(AccessMixin):
    """Réservé aux candidats connectés ; met la fiche dans self.candidat."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.candidat = candidat_de(request.user)
        if self.candidat is None:
            raise PermissionDenied('Espace réservé aux candidats.')
        return super().dispatch(request, *args, **kwargs)


class EspaceFormateurMixin(AccessMixin):
    """Réservé aux formateurs actifs connectés ; met la fiche dans self.formateur."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.formateur = formateur_de(request.user)
        if self.formateur is None:
            raise PermissionDenied('Espace réservé aux formateurs.')
        return super().dispatch(request, *args, **kwargs)


def peut_telecharger(utilisateur, document):
    """Règle de téléchargement d'un document de formation.

    - Document public d'une formation visible sur le site : tout le monde.
    - Personnel du centre ayant le droit de consulter les documents : toujours.
    - Candidat : seulement s'il a une inscription CONFIRMÉE ou TERMINÉE à une session de cette formation.
    - Formateur actif : seulement s'il anime une session (non annulée) de cette formation.
    """
    if document.est_public and Formation.objects.publiees().filter(pk=document.formation_id).exists():
        return True
    if not utilisateur.is_authenticated:
        return False
    if utilisateur.has_perm('catalog.view_documentformation'):
        return True
    candidat = candidat_de(utilisateur)
    if candidat and Inscription.objects.filter(
        candidat=candidat, session__formation_id=document.formation_id,
        statut__in=Inscription.STATUTS_OCCUPANT_UNE_PLACE,
    ).exists():
        return True
    formateur = formateur_de(utilisateur)
    if formateur and Session.objects.filter(formateur=formateur, formation_id=document.formation_id).exclude(
        statut=Session.Statut.ANNULEE,
    ).exists():
        return True
    return False
