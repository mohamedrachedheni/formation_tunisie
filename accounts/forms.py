from django import forms
from django.conf import settings
from django.contrib.auth.forms import (
    AuthenticationForm, PasswordResetForm, SetPasswordForm, UserChangeForm, UserCreationForm,
)
from django.core.cache import cache

from core.forms import FormulaireBootstrapMixin

from .jetons import encoder_identifiant
from .models import Utilisateur


class UtilisateurCreationForm(UserCreationForm):
    class Meta:
        model = Utilisateur
        fields = ('email', 'username', 'first_name', 'last_name')


class UtilisateurChangeForm(UserChangeForm):
    class Meta:
        model = Utilisateur
        fields = '__all__'


# --- Connexion (avec limitation des tentatives) -----------------------------------------------

def _cles_tentatives(request, email):
    adresse_ip = request.META.get('REMOTE_ADDR', 'inconnue') if request else 'inconnue'
    return [f'connexion:ip:{adresse_ip}', f'connexion:email:{(email or "").strip().lower()}']


class ConnexionForm(FormulaireBootstrapMixin, AuthenticationForm):
    """Connexion par email. Après CONNEXION_ECHECS_MAX échecs (par adresse IP ou par email),
    toute tentative est refusée pendant CONNEXION_DUREE_BLOCAGE secondes, même avec le bon mot de passe :
    cela freine les essais automatiques de mots de passe."""

    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': 'Email ou mot de passe incorrect.',
        'trop_de_tentatives': 'Trop de tentatives de connexion. Réessayez dans quelques minutes.',
    }

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields['username'].label = 'Adresse email'
        self.fields['username'].widget.attrs.update({'autocomplete': 'email', 'inputmode': 'email', 'autofocus': True})
        self.fields['password'].widget.attrs['autocomplete'] = 'current-password'

    def clean(self):
        cles = _cles_tentatives(self.request, self.data.get('username'))
        if any((cache.get(cle) or 0) >= settings.CONNEXION_ECHECS_MAX for cle in cles):
            raise forms.ValidationError(self.error_messages['trop_de_tentatives'], code='trop_de_tentatives')
        try:
            donnees = super().clean()
        except forms.ValidationError:
            for cle in cles:
                cache.add(cle, 0, settings.CONNEXION_DUREE_BLOCAGE)
                try:
                    cache.incr(cle)
                except ValueError:  # clé expirée entre-temps
                    cache.set(cle, 1, settings.CONNEXION_DUREE_BLOCAGE)
            raise
        cache.delete_many(cles)
        return donnees


# --- Mot de passe oublié et choix du mot de passe ----------------------------------------------

class MotDePasseOublieForm(FormulaireBootstrapMixin, PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].label = 'Adresse email'

    def send_mail(self, subject_template_name, email_template_name, context, from_email, to_email, html_email_template_name=None):
        # Le lien contient l'uuid du compte, jamais son id numérique.
        context['uid'] = encoder_identifiant(context['user'])
        super().send_mail(subject_template_name, email_template_name, context, from_email, to_email, html_email_template_name)


class ChoixMotDePasseForm(FormulaireBootstrapMixin, SetPasswordForm):
    pass
