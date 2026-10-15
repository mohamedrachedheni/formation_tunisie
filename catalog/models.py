import uuid
from pathlib import Path

from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from core.models import ModeleDeBase


def chemin_image_formation(instance, nom_fichier):
    # Nom de fichier aléatoire : évite les collisions et ne révèle pas le nom d'origine.
    return f'formations/images/{uuid.uuid4().hex}{Path(nom_fichier).suffix.lower()}'


def chemin_document_formation(instance, nom_fichier):
    # Nom aléatoire impossible à deviner : les documents non publics ne doivent pas être
    # accessibles en devinant leur adresse (protection complète prévue au niveau 3).
    return f'formations/documents/{uuid.uuid4().hex}{Path(nom_fichier).suffix.lower()}'


class SlugAutomatiqueMixin:
    """Génère le slug à partir du champ indiqué par `champ_source_slug` s'il est vide."""

    champ_source_slug = None

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(getattr(self, self.champ_source_slug))[:self._meta.get_field('slug').max_length]
        super().save(*args, **kwargs)


class Categorie(SlugAutomatiqueMixin, ModeleDeBase):
    champ_source_slug = 'nom'

    nom = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True, help_text='Adresse web, générée à partir du nom si vide.')
    description = models.TextField(blank=True)
    ordre = models.PositiveSmallIntegerField('ordre d’affichage', default=0)
    est_active = models.BooleanField('active', default=True, help_text='Une catégorie inactive masque ses formations sur le site.')

    class Meta:
        verbose_name = 'catégorie'
        verbose_name_plural = 'catégories'
        ordering = ['ordre', 'nom']

    def __str__(self):
        return self.nom


class FormationQuerySet(models.QuerySet):
    def publiees(self):
        # Règle de visibilité sur le site : formation publiée ET catégorie active.
        return self.filter(est_publiee=True, categorie__est_active=True)


class Formation(SlugAutomatiqueMixin, ModeleDeBase):
    champ_source_slug = 'titre'

    objects = FormationQuerySet.as_manager()

    class Niveau(models.TextChoices):
        DEBUTANT = 'debutant', 'Débutant'
        INTERMEDIAIRE = 'intermediaire', 'Intermédiaire'
        AVANCE = 'avance', 'Avancé'

    class Modalite(models.TextChoices):
        PRESENTIEL = 'presentiel', 'Présentiel'
        DISTANCE = 'distance', 'À distance'
        HYBRIDE = 'hybride', 'Hybride'

    # PROTECT : une catégorie qui contient des formations ne peut pas être supprimée.
    categorie = models.ForeignKey(Categorie, on_delete=models.PROTECT, related_name='formations', verbose_name='catégorie')
    titre = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True, help_text='Adresse web, générée à partir du titre si vide.')
    resume = models.CharField('résumé', max_length=300, help_text='Court texte affiché dans la liste des formations.')
    description = models.TextField(blank=True)
    objectifs = models.TextField(blank=True)
    public_vise = models.TextField('public visé', blank=True)
    prerequis = models.TextField('prérequis', blank=True)
    duree_heures = models.PositiveIntegerField('durée (heures)', validators=[MinValueValidator(1)])
    # Montant en dinars tunisiens : 3 décimales (millimes).
    prix = models.DecimalField('prix (TND)', max_digits=10, decimal_places=3, validators=[MinValueValidator(0)])
    niveau = models.CharField(max_length=20, choices=Niveau.choices, default=Niveau.DEBUTANT)
    modalite = models.CharField('modalité', max_length=20, choices=Modalite.choices, default=Modalite.PRESENTIEL)
    image = models.ImageField(upload_to=chemin_image_formation, blank=True)
    # Une formation non publiée reste visible dans l'administration mais pas sur le site.
    est_publiee = models.BooleanField('publiée', default=False)
    est_certifiante = models.BooleanField('certifiante', default=False)

    class Meta:
        verbose_name = 'formation'
        verbose_name_plural = 'formations'
        ordering = ['titre']
        constraints = [
            models.CheckConstraint(condition=models.Q(prix__gte=0), name='formation_prix_positif'),
            models.CheckConstraint(condition=models.Q(duree_heures__gt=0), name='formation_duree_positive'),
        ]
        indexes = [
            models.Index(fields=['est_publiee', 'categorie'], name='formation_publiee_cat_idx'),
        ]

    def __str__(self):
        return self.titre

    def get_absolute_url(self):
        return reverse('catalog:detail', kwargs={'slug': self.slug})


class ModuleProgramme(ModeleDeBase):
    # CASCADE : un module n'existe pas sans sa formation (il en fait partie).
    formation = models.ForeignKey(Formation, on_delete=models.CASCADE, related_name='modules')
    ordre = models.PositiveSmallIntegerField('ordre', default=1, validators=[MinValueValidator(1)])
    titre = models.CharField(max_length=200)
    contenu = models.TextField(blank=True)
    duree_heures = models.PositiveIntegerField('durée (heures)', null=True, blank=True, validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = 'module du programme'
        verbose_name_plural = 'modules du programme'
        ordering = ['formation', 'ordre']
        constraints = [
            # Deux modules d'une même formation ne peuvent pas avoir le même rang.
            models.UniqueConstraint(fields=['formation', 'ordre'], name='module_ordre_unique_par_formation'),
            models.CheckConstraint(condition=models.Q(ordre__gte=1), name='module_ordre_positif'),
            models.CheckConstraint(
                condition=models.Q(duree_heures__isnull=True) | models.Q(duree_heures__gt=0),
                name='module_duree_positive',
            ),
        ]

    def __str__(self):
        return f'{self.ordre}. {self.titre}'


class DocumentFormation(ModeleDeBase):
    EXTENSIONS_AUTORISEES = ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'odt', 'odp', 'ods', 'zip']

    formation = models.ForeignKey(Formation, on_delete=models.CASCADE, related_name='documents')
    titre = models.CharField(max_length=200)
    fichier = models.FileField(
        upload_to=chemin_document_formation,
        validators=[FileExtensionValidator(EXTENSIONS_AUTORISEES)],
    )
    # Public : téléchargeable sur la fiche de la formation (ex. brochure).
    # Non public : réservé aux inscrits (niveau 3).
    est_public = models.BooleanField('public', default=False)

    class Meta:
        verbose_name = 'document'
        verbose_name_plural = 'documents'
        ordering = ['formation', 'titre']

    def __str__(self):
        return self.titre
