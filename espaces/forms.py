from django import forms
from django.contrib.auth import get_user_model

from core.forms import FormulaireBootstrapMixin
from enrollments.models import Candidat


class ProfilCandidatForm(FormulaireBootstrapMixin, forms.ModelForm):
    """Le candidat ne modifie que son téléphone et son email ; le nom et la CIN restent gérés par le centre.

    L'email est aussi l'identifiant de connexion : il est obligatoire, unique parmi les comptes,
    et le changer met à jour l'email de connexion.
    """

    class Meta:
        model = Candidat
        fields = ('telephone', 'email')
        widgets = {
            'telephone': forms.TextInput(attrs={'autocomplete': 'tel', 'inputmode': 'tel'}),
            'email': forms.EmailInput(attrs={'autocomplete': 'email'}),
        }
        help_texts = {'email': 'Sert aussi à vous connecter à votre espace.'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        autres_comptes = get_user_model().objects.filter(email__iexact=email).exclude(pk=self.instance.utilisateur_id)
        if autres_comptes.exists():
            raise forms.ValidationError('Cette adresse email est déjà utilisée par un autre compte.')
        return email

    def save(self, commit=True):
        candidat = super().save(commit=commit)
        if commit and candidat.utilisateur_id:
            utilisateur = candidat.utilisateur
            if utilisateur.email != candidat.email:
                utilisateur.email = candidat.email
                utilisateur.save(update_fields=['email'])
        return candidat
