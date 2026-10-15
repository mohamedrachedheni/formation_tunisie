from django import forms

from catalog.models import Formation

from .models import DemandeContact


class DemandeContactForm(forms.ModelForm):
    # Champ piège (« honeypot ») : masqué aux visiteurs, mais rempli par les robots qui
    # complètent tous les champs. Une demande où il est rempli est ignorée (voir la vue).
    site_web = forms.CharField(required=False, label='Site web')

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
        self.fields['site_web'].widget.attrs.update({'tabindex': '-1', 'autocomplete': 'off'})
        # Classes Bootstrap
        for nom, champ in self.fields.items():
            if nom != 'site_web':
                classe = 'form-select' if isinstance(champ.widget, forms.Select) else 'form-control'
                champ.widget.attrs['class'] = classe

    def full_clean(self):
        super().full_clean()
        # Bordure rouge Bootstrap sur les champs en erreur.
        for nom in self.errors:
            if nom in self.fields:
                self.fields[nom].widget.attrs['class'] += ' is-invalid'

    def clean(self):
        donnees = super().clean()
        # Même règle que la contrainte en base, avec un message compréhensible.
        if not donnees.get('email') and not donnees.get('telephone') and not self.has_error('email') and not self.has_error('telephone'):
            raise forms.ValidationError('Indiquez au moins un email ou un numéro de téléphone pour que nous puissions vous répondre.')
        return donnees

    def est_spam(self):
        return bool(self.cleaned_data.get('site_web'))
