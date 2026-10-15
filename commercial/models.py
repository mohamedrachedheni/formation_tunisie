from django.conf import settings
from django.db import models

from catalog.models import Formation
from core.models import ModeleDeBase
from core.validators import valider_telephone


class DemandeContact(ModeleDeBase):
    """Demande d'information d'un visiteur ou d'un prospect, à traiter par le centre."""

    class Source(models.TextChoices):
        FORMULAIRE = 'formulaire', 'Formulaire du site'
        WHATSAPP = 'whatsapp', 'WhatsApp'
        TELEPHONE = 'telephone', 'Téléphone'

    class Statut(models.TextChoices):
        NOUVELLE = 'nouvelle', 'Nouvelle'
        EN_COURS = 'en_cours', 'En cours'
        TRAITEE = 'traitee', 'Traitée'

    nom = models.CharField('nom et prénom', max_length=150)
    email = models.EmailField(blank=True)
    telephone = models.CharField('téléphone', max_length=20, blank=True, validators=[valider_telephone])
    message = models.TextField()
    # SET_NULL : la demande est conservée même si la formation concernée disparaît.
    formation = models.ForeignKey(
        Formation, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='demandes_contact', verbose_name='formation concernée',
    )
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.FORMULAIRE)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.NOUVELLE)
    traitee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='demandes_contact_traitees', verbose_name='traitée par',
    )
    notes = models.TextField('notes internes', blank=True, help_text='Non visibles par le demandeur.')

    class Meta:
        verbose_name = 'demande de contact'
        verbose_name_plural = 'demandes de contact'
        ordering = ['-date_creation']
        constraints = [
            # Le centre doit pouvoir répondre : au moins un moyen de contact.
            models.CheckConstraint(
                condition=~models.Q(email='') | ~models.Q(telephone=''),
                name='demande_contact_email_ou_telephone',
            ),
        ]
        indexes = [
            models.Index(fields=['statut', 'date_creation'], name='demande_statut_date_idx'),
        ]

    def __str__(self):
        return f'{self.nom} — {self.date_creation:%d/%m/%Y}' if self.date_creation else self.nom
