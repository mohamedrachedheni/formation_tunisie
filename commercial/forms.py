from django import forms

from catalog.models import Formation
from core.forms import FormulairePublicMixin

from .models import DemandeContact


class DemandeContactForm(FormulairePublicMixin, forms.ModelForm):
    # Le champ piège anti-spam et les classes Bootstrap viennent de FormulairePublicMixin.

    # Identifiant public (uuid) dans le formulaire : jamais l'id numérique.
    # Seules les formations visibles sur le site peuvent être choisies.
    formation = forms.ModelChoiceField(
        queryset=Formation.objects.none(),
        to_field_name='uuid',
        required=False,
        empty_label='— Aucune en particulier —',
        label='Formation concernée',
    )

    class Meta:
        model = DemandeContact
        fields = ('nom', 'email', 'telephone', 'formation', 'message')
        widgets = {
            'nom': forms.TextInput(attrs={'autocomplete': 'name'}),
            'email': forms.EmailInput(attrs={'autocomplete': 'email'}),
            'telephone': forms.TextInput(attrs={'autocomplete': 'tel', 'inputmode': 'tel'}),
            'message': forms.Textarea(attrs={'rows': 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['formation'].queryset = Formation.objects.publiees().order_by('titre')

    def clean(self):
        donnees = super().clean()
        # Même règle que la contrainte en base, avec un message compréhensible.
        if not donnees.get('email') and not donnees.get('telephone') and not self.has_error('email') and not self.has_error('telephone'):
            raise forms.ValidationError('Indiquez au moins un email ou un numéro de téléphone pour que nous puissions vous répondre.')
        return donnees
