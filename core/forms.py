from django import forms


class FormulaireBootstrapMixin:
    """Classes Bootstrap sur les champs, et `is-invalid` sur les champs en erreur.

    À rendre avec le gabarit `core/_champs_formulaire.html`.
    """

    CHAMPS_SANS_STYLE = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nom, champ in self.fields.items():
            if nom in self.CHAMPS_SANS_STYLE:
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
            if nom in self.fields and nom not in self.CHAMPS_SANS_STYLE:
                self.fields[nom].widget.attrs['class'] = self.fields[nom].widget.attrs.get('class', '') + ' is-invalid'


class FormulairePublicMixin(FormulaireBootstrapMixin):
    """Formulaires du site public : classes Bootstrap et champ piège anti-spam `site_web` (« honeypot »).

    Le champ piège est placé hors écran : seuls les robots qui complètent tous les champs le remplissent.
    La vue appelle `est_spam()` et, dans ce cas, n'enregistre rien tout en affichant la réponse habituelle
    (pour ne pas révéler la protection).
    """

    CHAMP_PIEGE = 'site_web'
    CHAMPS_SANS_STYLE = (CHAMP_PIEGE,)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ajouté après la mise en forme Bootstrap : le champ piège ne reçoit aucune classe visible.
        self.fields[self.CHAMP_PIEGE] = forms.CharField(
            required=False, label='Site web',
            widget=forms.TextInput(attrs={'tabindex': '-1', 'autocomplete': 'off'}),
        )

    def est_spam(self):
        return bool(self.cleaned_data.get(self.CHAMP_PIEGE))
