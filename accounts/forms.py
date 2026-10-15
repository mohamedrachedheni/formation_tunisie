from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import Utilisateur


class UtilisateurCreationForm(UserCreationForm):
    class Meta:
        model = Utilisateur
        fields = ('email', 'username', 'first_name', 'last_name')


class UtilisateurChangeForm(UserChangeForm):
    class Meta:
        model = Utilisateur
        fields = '__all__'
