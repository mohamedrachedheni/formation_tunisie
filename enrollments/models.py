from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Count, Q

from catalog.models import Formation
from core.constantes import Gouvernorat
from core.models import ModeleDeBase
from core.validators import normaliser_telephone, valider_telephone
from trainers.models import Formateur

# Numéro de carte d'identité nationale tunisienne : 8 chiffres.
valider_cin = RegexValidator(r'^[0-9]{8}$', 'Le numéro de CIN doit comporter exactement 8 chiffres.')


# --- Session --------------------------------------------------------------------------------

class SessionQuerySet(models.QuerySet):
    def visibles(self):
        # Règle de visibilité sur le site : session publiée, inscriptions ouvertes,
        # et formation elle-même visible (publiée, catégorie active).
        return self.filter(
            est_publiee=True,
            statut=Session.Statut.OUVERTE,
            formation__est_publiee=True,
            formation__categorie__est_active=True,
        )

    def avec_places_occupees(self):
        return self.annotate(
            nb_places_occupees=Count('inscriptions', filter=Q(inscriptions__statut__in=Inscription.STATUTS_OCCUPANT_UNE_PLACE)),
        )


class Session(ModeleDeBase):
    """Réalisation datée d'une formation (dates, lieu, formateur, nombre de places)."""

    class Statut(models.TextChoices):
        PLANIFIEE = 'planifiee', 'Planifiée'
        OUVERTE = 'ouverte', 'Inscriptions ouvertes'
        EN_COURS = 'en_cours', 'En cours'
        TERMINEE = 'terminee', 'Terminée'
        ANNULEE = 'annulee', 'Annulée'

    # PROTECT : une formation ou un formateur ayant des sessions ne peut pas être supprimé.
    formation = models.ForeignKey(Formation, on_delete=models.PROTECT, related_name='sessions')
    formateur = models.ForeignKey(
        Formateur, on_delete=models.PROTECT, null=True, blank=True, related_name='sessions',
        help_text='Peut être désigné plus tard.',
    )
    code = models.CharField(
        max_length=50, unique=True, blank=True,
        help_text='Référence interne, générée automatiquement si vide (ex. EXCEL-2026-11).',
    )
    date_debut = models.DateField('date de début')
    date_fin = models.DateField('date de fin')
    horaires = models.CharField(max_length=150, blank=True, help_text='Ex. : samedi 9h–13h.')
    lieu = models.CharField(max_length=200, blank=True)
    modalite = models.CharField(
        'modalité', max_length=20, choices=Formation.Modalite.choices, blank=True,
        help_text='Reprend celle de la formation si vide.',
    )
    places_max = models.PositiveSmallIntegerField('nombre de places', validators=[MinValueValidator(1)])
    # Prix propre à la session (promotion, session intensive…). Vide : prix de la formation.
    prix = models.DecimalField(
        'prix (TND)', max_digits=10, decimal_places=3, null=True, blank=True, validators=[MinValueValidator(0)],
        help_text='Laisser vide pour appliquer le prix de la formation.',
    )
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.PLANIFIEE)
    est_publiee = models.BooleanField('publiée', default=False)

    objects = SessionQuerySet.as_manager()

    class Meta:
        verbose_name = 'session'
        verbose_name_plural = 'sessions'
        ordering = ['-date_debut']
        constraints = [
            models.CheckConstraint(condition=Q(date_fin__gte=models.F('date_debut')), name='session_dates_coherentes'),
            models.CheckConstraint(condition=Q(places_max__gt=0), name='session_places_positives'),
            models.CheckConstraint(condition=Q(prix__isnull=True) | Q(prix__gte=0), name='session_prix_positif'),
        ]
        indexes = [
            models.Index(fields=['statut', 'date_debut'], name='session_statut_date_idx'),
            models.Index(fields=['est_publiee', 'date_debut'], name='session_publiee_date_idx'),
        ]

    def __str__(self):
        return f'{self.formation} — {self.date_debut:%d/%m/%Y}'

    @property
    def prix_effectif(self):
        return self.prix if self.prix is not None else self.formation.prix

    @property
    def places_occupees(self):
        # Valeur annotée si disponible (listes), sinon requête.
        if hasattr(self, 'nb_places_occupees'):
            return self.nb_places_occupees
        return self.inscriptions.filter(statut__in=Inscription.STATUTS_OCCUPANT_UNE_PLACE).count()

    @property
    def places_restantes(self):
        return max(self.places_max - self.places_occupees, 0)

    @property
    def accepte_les_inscriptions(self):
        return self.statut == self.Statut.OUVERTE

    def clean(self):
        super().clean()
        erreurs = {}
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            erreurs['date_fin'] = 'La date de fin doit être postérieure ou égale à la date de début.'
        # Seul un formateur actif peut être affecté (un formateur déjà affecté puis désactivé reste accepté).
        if self.formateur_id and not self.formateur.est_actif:
            ancien = None if self._state.adding else type(self).objects.filter(pk=self.pk).values_list('formateur_id', flat=True).first()
            if ancien != self.formateur_id:
                erreurs['formateur'] = 'Ce formateur est inactif : il ne peut pas être affecté à une session.'
        # On ne peut pas réduire le nombre de places en dessous des inscriptions confirmées.
        if self.pk and self.places_max and self.places_max < self.places_occupees:
            erreurs['places_max'] = f'{self.places_occupees} place(s) sont déjà occupées par des inscriptions confirmées.'
        if erreurs:
            raise ValidationError(erreurs)

    def save(self, *args, **kwargs):
        if not self.modalite and self.formation_id:
            self.modalite = self.formation.modalite
        if not self.code:
            self.code = self._generer_code()
        super().save(*args, **kwargs)

    def _generer_code(self):
        base = f'{self.formation.slug[:30].upper()}-{self.date_debut:%Y-%m}'
        code, numero = base, 2
        while type(self).objects.filter(code=code).exists():
            code, numero = f'{base}-{numero}', numero + 1
        return code


# --- Candidat -------------------------------------------------------------------------------

class Candidat(ModeleDeBase):
    """Personne intéressée ou inscrite à une session. Peut exister sans compte utilisateur."""

    class NiveauEtudes(models.TextChoices):
        PRIMAIRE = 'primaire', 'Primaire'
        SECONDAIRE = 'secondaire', 'Secondaire'
        BAC = 'bac', 'Baccalauréat'
        BAC_2 = 'bac_2', 'Bac + 2 (BTS, DUT…)'
        LICENCE = 'licence', 'Licence (Bac + 3)'
        MASTER = 'master', 'Master / ingénieur (Bac + 5)'
        DOCTORAT = 'doctorat', 'Doctorat'
        AUTRE = 'autre', 'Autre'

    # Compte facultatif, donné au niveau 3 pour l'espace candidat.
    utilisateur = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='candidat', verbose_name='compte utilisateur',
    )
    nom = models.CharField(max_length=100)
    prenom = models.CharField('prénom', max_length=100)
    # Le téléphone est obligatoire (moyen de contact principal, WhatsApp) ; l'email est facultatif.
    telephone = models.CharField('téléphone', max_length=20, validators=[valider_telephone])
    email = models.EmailField(blank=True)
    # CIN facultative mais unique : une valeur vide est stockée NULL (non soumise à l'unicité).
    cin = models.CharField('CIN', max_length=8, null=True, blank=True, unique=True, validators=[valider_cin])
    date_naissance = models.DateField('date de naissance', null=True, blank=True)
    gouvernorat = models.CharField(max_length=20, choices=Gouvernorat.choices, blank=True)
    niveau_etudes = models.CharField('niveau d’études', max_length=20, choices=NiveauEtudes.choices, blank=True)
    profession = models.CharField(max_length=150, blank=True)

    class Meta:
        verbose_name = 'candidat'
        verbose_name_plural = 'candidats'
        ordering = ['nom', 'prenom']
        constraints = [
            models.CheckConstraint(condition=Q(cin__isnull=True) | Q(cin__regex=r'^[0-9]{8}$'), name='candidat_cin_8_chiffres'),
        ]
        indexes = [
            # Recherche d'un candidat existant lors d'une pré-inscription (téléphone ou email).
            models.Index(fields=['telephone'], name='candidat_telephone_idx'),
            models.Index(fields=['email'], name='candidat_email_idx'),
        ]

    def __str__(self):
        return f'{self.nom_complet} ({self.telephone})'

    @property
    def nom_complet(self):
        return f'{self.prenom} {self.nom}'

    def save(self, *args, **kwargs):
        self.email = (self.email or '').strip().lower()
        self.cin = (self.cin or '').strip() or None
        # Forme unique du téléphone (ex. « +216 98 123 456 » → « 98123456 ») : permet de retrouver
        # un candidat existant quelle que soit la façon dont le numéro a été saisi.
        self.telephone = normaliser_telephone(self.telephone)
        super().save(*args, **kwargs)


# --- Inscription ----------------------------------------------------------------------------

class Inscription(ModeleDeBase):
    """Inscription d'un candidat à une session.

    Cycle de vie (les changements de statut passent par enrollments.services) :
    en attente → confirmée → terminée (avec résultat) ; en attente ou confirmée → annulée ;
    annulée → en attente (réinscription : on réactive la même ligne, jamais de doublon).
    """

    class Statut(models.TextChoices):
        EN_ATTENTE = 'en_attente', 'En attente'
        CONFIRMEE = 'confirmee', 'Confirmée'
        ANNULEE = 'annulee', 'Annulée'
        TERMINEE = 'terminee', 'Terminée'

    class Resultat(models.TextChoices):
        REUSSI = 'reussi', 'Réussi'
        ECHOUE = 'echoue', 'Échoué'

    class Source(models.TextChoices):
        SITE = 'site', 'Site web'
        WHATSAPP = 'whatsapp', 'WhatsApp'
        TELEPHONE = 'telephone', 'Téléphone'
        SUR_PLACE = 'sur_place', 'Sur place'

    # Seules les inscriptions confirmées ou terminées occupent une place.
    # Les inscriptions en attente forment de fait une liste d'attente.
    STATUTS_OCCUPANT_UNE_PLACE = (Statut.CONFIRMEE, Statut.TERMINEE)

    # PROTECT : on ne supprime ni un candidat ni une session qui ont des inscriptions.
    candidat = models.ForeignKey(Candidat, on_delete=models.PROTECT, related_name='inscriptions')
    session = models.ForeignKey(Session, on_delete=models.PROTECT, related_name='inscriptions')
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE)
    resultat = models.CharField('résultat', max_length=20, choices=Resultat.choices, blank=True)
    # Prix figé au moment de l'inscription : une modification ultérieure du tarif ne change pas l'historique.
    prix_convenu = models.DecimalField('prix convenu (TND)', max_digits=10, decimal_places=3, validators=[MinValueValidator(0)])
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.SITE)
    date_confirmation = models.DateTimeField('date de confirmation', null=True, blank=True)
    notes = models.TextField('notes internes', blank=True)

    class Meta:
        verbose_name = 'inscription'
        verbose_name_plural = 'inscriptions'
        ordering = ['-date_creation']
        permissions = [
            ('valider_inscription', 'Peut confirmer, annuler ou clôturer une inscription'),
        ]
        constraints = [
            # Un candidat ne s'inscrit qu'une fois à une même session.
            models.UniqueConstraint(fields=['candidat', 'session'], name='inscription_unique_candidat_session'),
            models.CheckConstraint(condition=Q(prix_convenu__gte=0), name='inscription_prix_positif'),
            # Un résultat n'existe que pour une inscription terminée.
            models.CheckConstraint(
                condition=Q(resultat='') | Q(statut='terminee'), name='inscription_resultat_si_terminee',
            ),
            # Une inscription confirmée ou terminée a forcément une date de confirmation.
            models.CheckConstraint(
                condition=~Q(statut__in=['confirmee', 'terminee']) | Q(date_confirmation__isnull=False),
                name='inscription_date_confirmation',
            ),
        ]
        indexes = [
            models.Index(fields=['session', 'statut'], name='inscription_session_statut_idx'),
        ]

    def __str__(self):
        return f'{self.candidat.nom_complet} — {self.session}'

    @property
    def occupe_une_place(self):
        return self.statut in self.STATUTS_OCCUPANT_UNE_PLACE
