from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

from core.fichiers import CheminAleatoire
from core.models import ModeleDeBase
from core.validators import valider_telephone


class FormateurQuerySet(models.QuerySet):
    def actifs(self):
        return self.filter(est_actif=True)

    def visibles(self):
        # Formateurs affichables sur le site public.
        return self.filter(est_actif=True, est_visible_site=True)


class Formateur(ModeleDeBase):
    """Formateur du centre. Peut exister sans compte utilisateur (affichage, affectation aux sessions)."""

    # Compte facultatif, donné au niveau 3 pour l'espace formateur.
    # SET_NULL : la suppression d'un compte ne supprime pas la fiche du formateur.
    utilisateur = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='formateur', verbose_name='compte utilisateur',
    )
    nom = models.CharField(max_length=100)
    prenom = models.CharField('prénom', max_length=100)
    # null=True : plusieurs formateurs peuvent ne pas avoir d'email, mais deux formateurs
    # ne peuvent pas partager le même email (une valeur vide est stockée NULL, non soumise à l'unicité).
    email = models.EmailField(blank=True, null=True, unique=True)
    telephone = models.CharField('téléphone', max_length=20, blank=True, validators=[valider_telephone])
    specialite = models.CharField('spécialité', max_length=150, blank=True)
    biographie = models.TextField(blank=True, help_text='Présentation affichée sur le site si le formateur est visible.')
    photo = models.ImageField(upload_to=CheminAleatoire('formateurs/photos'), blank=True)
    # Donnée personnelle : à ne jamais afficher sur le site public.
    cv = models.FileField(
        'CV', upload_to=CheminAleatoire('formateurs/cv'), blank=True,
        validators=[FileExtensionValidator(['pdf', 'doc', 'docx', 'odt'])],
    )
    est_actif = models.BooleanField('actif', default=True, help_text='Un formateur inactif ne peut plus être affecté à une session.')
    est_visible_site = models.BooleanField('visible sur le site', default=False)

    objects = FormateurQuerySet.as_manager()

    class Meta:
        verbose_name = 'formateur'
        verbose_name_plural = 'formateurs'
        ordering = ['nom', 'prenom']
        constraints = [
            # Un formateur inactif n'est jamais présenté sur le site.
            models.CheckConstraint(
                condition=~models.Q(est_actif=False, est_visible_site=True),
                name='formateur_visible_seulement_si_actif',
            ),
        ]

    def __str__(self):
        return self.nom_complet

    @property
    def nom_complet(self):
        return f'{self.prenom} {self.nom}'

    def clean(self):
        super().clean()
        if self.est_visible_site and not self.est_actif:
            raise ValidationError({'est_visible_site': 'Un formateur inactif ne peut pas être visible sur le site.'})

    def save(self, *args, **kwargs):
        # Email en minuscules, et NULL plutôt que chaîne vide (voir le champ email).
        email = (self.email or '').strip().lower()
        self.email = email or None
        super().save(*args, **kwargs)
