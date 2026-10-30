"""Jetons et identifiants des liens envoyés aux utilisateurs (invitation, mot de passe oublié)."""

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import ValidationError
from django.utils.crypto import constant_time_compare
from django.utils.encoding import force_bytes, force_str
from django.utils.http import base36_to_int, urlsafe_base64_decode, urlsafe_base64_encode


class GenerateurInvitation(PasswordResetTokenGenerator):
    """Jeton du lien d'invitation (activation du compte).

    Même mécanisme sécurisé que « mot de passe oublié » (jeton signé avec SECRET_KEY), avec :
    - un sel différent : un jeton d'invitation ne vaut pas pour une réinitialisation, et inversement ;
    - une durée propre (settings.DUREE_VALIDITE_INVITATION, 7 jours).
    Le jeton devient invalide dès que le mot de passe est choisi (usage unique).
    """

    key_salt = 'accounts.jetons.GenerateurInvitation'

    def check_token(self, user, token):
        # Reprend PasswordResetTokenGenerator.check_token avec la durée de validité de l'invitation.
        if not (user and token):
            return False
        try:
            horodatage_b36, _ = token.split('-')
            horodatage = base36_to_int(horodatage_b36)
        except ValueError:
            return False
        for secret in [self.secret, *self.secret_fallbacks]:
            if constant_time_compare(self._make_token_with_timestamp(user, horodatage, secret), token):
                break
        else:
            return False
        return (self._num_seconds(self._now()) - horodatage) <= settings.DUREE_VALIDITE_INVITATION


generateur_invitation = GenerateurInvitation()


def encoder_identifiant(utilisateur):
    """Identifiant public placé dans les liens : l'uuid du compte (jamais l'id numérique)."""
    return urlsafe_base64_encode(force_bytes(str(utilisateur.uuid)))


def utilisateur_depuis_identifiant(identifiant):
    """Compte correspondant à l'identifiant d'un lien, ou None si le lien est invalide ou altéré."""
    from django.contrib.auth import get_user_model

    Utilisateur = get_user_model()
    try:
        return Utilisateur._default_manager.get(uuid=force_str(urlsafe_base64_decode(identifiant)))
    except (TypeError, ValueError, OverflowError, ValidationError, Utilisateur.DoesNotExist):
        return None
