from django import forms

from core.forms import FormulairePublicMixin

from .models import Candidat, Inscription
from .services import verifier_inscription_possible


class PreInscriptionForm(FormulairePublicMixin, forms.ModelForm):
    """Pré-inscription publique à une session (champ piège anti-spam inclus via le mixin)."""

    message = forms.CharField(
        label='Message (facultatif)', required=False, max_length=2000,
        widget=forms.Textarea(attrs={'rows': 3}),
    )
    consentement = forms.BooleanField(
        label='J’accepte que mes données soient utilisées par le centre pour traiter ma demande d’inscription.',
        required=True,
    )

    class Meta:
        model = Candidat
        fields = ('prenom', 'nom', 'telephone', 'email', 'cin', 'date_naissance', 'gouvernorat', 'niveau_etudes', 'profession')
        widgets = {
            'prenom': forms.TextInput(attrs={'autocomplete': 'given-name'}),
            'nom': forms.TextInput(attrs={'autocomplete': 'family-name'}),
            'telephone': forms.TextInput(attrs={'autocomplete': 'tel', 'inputmode': 'tel'}),
            'email': forms.EmailInput(attrs={'autocomplete': 'email'}),
            'cin': forms.TextInput(attrs={'inputmode': 'numeric', 'maxlength': 8}),
            'date_naissance': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }
        help_texts = {
            'telephone': 'Nous vous contacterons à ce numéro (appel ou WhatsApp).',
            'cin': 'Facultatif — 8 chiffres.',
        }

    def validate_unique(self):
        # Une CIN déjà connue n'est pas une erreur : elle sert à retrouver le candidat existant
        # (voir services.pre_inscrire). Le format de la CIN reste vérifié.
        pass


class InscriptionAjoutForm(forms.ModelForm):
    """Ajout d'une inscription depuis l'administration (le prix est facultatif : prix de la session par défaut)."""

    class Meta:
        model = Inscription
        fields = ('candidat', 'session', 'source', 'prix_convenu', 'notes')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['prix_convenu'].required = False
        self.fields['prix_convenu'].help_text = 'Laisser vide pour appliquer le prix de la session.'

    def clean(self):
        donnees = super().clean()
        candidat, session = donnees.get('candidat'), donnees.get('session')
        if candidat and session:
            verifier_inscription_possible(candidat, session)
        return donnees

    def _get_validation_exclusions(self):
        exclusions = super()._get_validation_exclusions()
        # L'unicité (candidat, session) est gérée par le service (clean() + inscrire) : une inscription
        # annulée est réactivée au lieu d'être refusée comme doublon. Les deux champs restent validés
        # par le formulaire ; seule la contrainte d'unicité du modèle est ainsi écartée ici.
        exclusions.update({'candidat', 'session'})
        # Un prix vide est complété par le service à l'enregistrement : il ne doit pas
        # être refusé ici par la validation du modèle (qui exige un prix).
        if self.cleaned_data.get('prix_convenu') is None:
            exclusions.add('prix_convenu')
        return exclusions
