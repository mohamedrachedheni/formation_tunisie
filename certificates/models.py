from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse

from core.models import ModeleDeBase
from enrollments.models import Inscription


class Certificat(ModeleDeBase):
    """Attestation de participation ou certificat de réussite délivré pour une inscription terminée.

    Le contenu imprimé (titulaire, formation, dates, signataire) est recopié à la délivrance :
    le document reste identique même si la fiche du candidat, la formation ou les paramètres du centre
    changent ensuite. Une correction se fait par l'action « Mettre à jour depuis l'inscription ».
    """

    class Type(models.TextChoices):
        PARTICIPATION = 'participation', 'Attestation de participation'
        REUSSITE = 'reussite', 'Certificat de réussite'

    class Statut(models.TextChoices):
        VALIDE = 'valide', 'Valide'
        ANNULE = 'annule', 'Annulé'

    PREFIXE_NUMERO = 'CERT'

    # Un seul certificat par inscription (donc par candidat et par session) ; PROTECT : une inscription
    # certifiée ne peut pas être supprimée.
    inscription = models.OneToOneField(Inscription, on_delete=models.PROTECT, related_name='certificat')
    # Numéro imprimé sur le document : CERT-AAAA-NNNNN, séquentiel par année de délivrance.
    numero = models.CharField('numéro', max_length=20, unique=True, editable=False)
    type = models.CharField(max_length=20, choices=Type.choices)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.VALIDE)
    date_delivrance = models.DateField('date de délivrance')
    delivre_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='certificats_delivres', verbose_name='délivré par',
    )

    # Contenu imprimé, recopié à la délivrance.
    titulaire = models.CharField(max_length=210)
    formation_titre = models.CharField('formation', max_length=200)
    duree_heures = models.PositiveIntegerField('durée (heures)')
    date_debut = models.DateField('début de la session')
    date_fin = models.DateField('fin de la session')
    signataire_nom = models.CharField('nom du signataire', max_length=150, blank=True)
    signataire_fonction = models.CharField('fonction du signataire', max_length=100, blank=True)

    # Annulation : le certificat est conservé (jamais supprimé) et la page de vérification l'indique.
    motif_annulation = models.TextField('motif d’annulation', blank=True)
    date_annulation = models.DateTimeField('date d’annulation', null=True, blank=True)

    class Meta:
        verbose_name = 'certificat'
        verbose_name_plural = 'certificats'
        ordering = ['-date_delivrance', '-numero']
        permissions = [
            ('delivrer_certificat', 'Peut délivrer et mettre à jour les certificats'),
            ('annuler_certificat', 'Peut annuler les certificats'),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(type__in=['participation', 'reussite']), name='certificat_type_valide'),
            models.CheckConstraint(condition=Q(statut__in=['valide', 'annule']), name='certificat_statut_valide'),
            # Un certificat annulé a toujours un motif et une date d'annulation.
            models.CheckConstraint(
                condition=Q(statut='valide') | (~Q(motif_annulation='') & Q(date_annulation__isnull=False)),
                name='certificat_annule_avec_motif',
            ),
            models.CheckConstraint(condition=Q(date_fin__gte=models.F('date_debut')), name='certificat_dates_coherentes'),
        ]

    def __str__(self):
        return f'{self.numero} — {self.titulaire}'

    @property
    def est_valide(self):
        return self.statut == self.Statut.VALIDE

    def get_absolute_url(self):
        # Page publique de vérification (adresse du QR code).
        return reverse('certificates:verifier', kwargs={'uuid': self.uuid})
