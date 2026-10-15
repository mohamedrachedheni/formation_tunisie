from django import forms


class FormulairePublicMixin:
    """Comportements communs aux formulaires du site public.

    - Champ piège anti-spam `site_web` (« honeypot ») : placé hors écran, il n'est rempli que par
      les robots qui complètent tous les champs. La vue appelle `est_spam()` et, dans ce cas,
      n'enregistre rien tout en affichant la réponse habituelle (pour ne pas révéler la protection).
    - Classes Bootstrap sur les champs, et `is-invalid` sur les champs en erreur.

    À rendre avec le gabarit `core/_champs_formulaire.html`.
    """

    CHAMP_PIEGE = 'site_web'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[self.CHAMP_PIEGE] = forms.CharField(
            required=False, label='Site web',
            widget=forms.TextInput(attrs={'tabindex': '-1', 'autocomplete': 'off'}),
        )
        for nom, champ in self.fields.items():
            if nom == self.CHAMP_PIEGE:
                continue
            if isinstance(champ.widget, forms.CheckboxInput):
                classe = 'form-check-input'
            elif isinstance(champ.widget, forms.Select):
                classe = 'form-select'
            else:
                classe = 'form-control'
            champ.widget.attrs['class'] = classe

    def full_clean(self):
        super().full_clean()
        for nom in self.errors:
            if nom in self.fields and nom != self.CHAMP_PIEGE:
                self.fields[nom].widget.attrs['class'] += ' is-invalid'

    def est_spam(self):
        return bool(self.cleaned_data.get(self.CHAMP_PIEGE))
