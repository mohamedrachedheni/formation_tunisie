from django.contrib import messages
from django.contrib.auth import views as vues_auth
from django.urls import reverse_lazy

from .forms import ChoixMotDePasseForm, ConnexionForm, MotDePasseOublieForm
from .jetons import generateur_invitation, utilisateur_depuis_identifiant


class ConnexionView(vues_auth.LoginView):
    template_name = 'accounts/connexion.html'
    authentication_form = ConnexionForm
    redirect_authenticated_user = True


class DeconnexionView(vues_auth.LogoutView):
    # Django n'accepte la déconnexion qu'en POST (protection contre les déconnexions forcées par lien).
    pass


class MotDePasseOublieView(vues_auth.PasswordResetView):
    template_name = 'accounts/mot_de_passe_oublie.html'
    form_class = MotDePasseOublieForm
    email_template_name = 'accounts/emails/mot_de_passe_oublie.txt'
    subject_template_name = 'accounts/emails/mot_de_passe_oublie_sujet.txt'
    success_url = reverse_lazy('accounts:mot_de_passe_oublie_envoye')


class MotDePasseOublieEnvoyeView(vues_auth.PasswordResetDoneView):
    # Même message que l'email existe ou non : on ne révèle pas quels emails ont un compte.
    template_name = 'accounts/mot_de_passe_oublie_envoye.html'


class LienParUuidMixin:
    """Retrouve le compte par son uuid (placé dans le lien) au lieu de l'id numérique de Django."""

    def get_user(self, uidb64):
        return utilisateur_depuis_identifiant(uidb64)


class ReinitialisationView(LienParUuidMixin, vues_auth.PasswordResetConfirmView):
    template_name = 'accounts/choix_mot_de_passe.html'
    form_class = ChoixMotDePasseForm
    success_url = reverse_lazy('accounts:reinitialisation_terminee')
    extra_context = {'titre_page': 'Nouveau mot de passe'}


class ReinitialisationTermineeView(vues_auth.PasswordResetCompleteView):
    template_name = 'accounts/reinitialisation_terminee.html'


class ActivationView(LienParUuidMixin, vues_auth.PasswordResetConfirmView):
    """Activation du compte depuis le lien d'invitation : la personne choisit son mot de passe,
    puis elle est connectée et dirigée vers son espace."""

    template_name = 'accounts/choix_mot_de_passe.html'
    form_class = ChoixMotDePasseForm
    token_generator = generateur_invitation
    post_reset_login = True
    success_url = reverse_lazy('espaces:tableau')
    extra_context = {'titre_page': 'Activer mon compte', 'activation': True}

    def form_valid(self, form):
        reponse = super().form_valid(form)
        messages.success(self.request, 'Votre compte est activé. Bienvenue dans votre espace !')
        return reponse
