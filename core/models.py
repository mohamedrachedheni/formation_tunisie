import uuid

from django.core.exceptions import ValidationError
from django.db import models


class ModeleDeBase(models.Model):
    """Modèle abstrait dont héritent tous les modèles métier du projet."""

    # Identifiant public : seul identifiant utilisé dans les URL, vues et formulaires.
    # La clé primaire numérique (id) reste interne à la base de données.
    uuid = models.UUIDField('identifiant public', default=uuid.uuid4, unique=True, editable=False)
    date_creation = models.DateTimeField('date de création', auto_now_add=True)
    date_modification = models.DateTimeField('date de modification', auto_now=True)

    class Meta:
        abstract = True


class ParametresCentre(ModeleDeBase):
    """Coordonnées et informations du centre affichées sur le site."""

    # Le centre est unique : la table ne contient qu'une seule ligne.
    # Garanti par la base : `verrou` vaut toujours True (CHECK) et doit être unique (UNIQUE).
    # (MariaDB n'accepte pas de CHECK sur la colonne id, qui est en AUTO_INCREMENT.)
    verrou = models.BooleanField(default=True, unique=True, editable=False)

    nom =models.CharField('nom du centre', max_length=150)
    slogan = models.CharField(max_length=255, blank=True)
    presentation = models.TextField('présentation', blank=True)
    adresse = models.CharField(max_length=255, blank=True)
    ville = models.CharField(max_length=100, blank=True)
    telephone = models.CharField('téléphone', max_length=20, blank=True)
    whatsapp = models.CharField(
        'numéro WhatsApp',
        max_length=20,
        blank=True,
        help_text='Format international sans « + » ni espaces, par exemple 21612345678.',
    )
    email = models.EmailField(blank=True)
    matricule_fiscal = models.CharField('matricule fiscal', max_length=30, blank=True)
    logo = models.ImageField(upload_to='centre/', blank=True)
    facebook = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    linkedin = models.URLField(blank=True)

    class Meta:
        verbose_name = 'paramètres du centre'
        verbose_name_plural = 'paramètres du centre'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(verrou=True),
                name='parametres_centre_ligne_unique',
            ),
        ]

    def __str__(self):
        return self.nom

    def validate_unique(self, exclude=None):
        # Message explicite à la place du message générique sur le champ technique `verrou`.
        if self._state.adding and type(self).objects.exists():
            raise ValidationError('Les paramètres du centre existent déjà : modifiez-les au lieu d’en créer de nouveaux.')
        super().validate_unique(exclude=exclude)

    @classmethod
    def obtenir(cls):
        """Retourne les paramètres du centre, ou None s'ils n'ont pas encore été saisis."""
        return cls.objects.first()

    @property
    def lien_whatsapp(self):
        return f'https://wa.me/{self.whatsapp}' if self.whatsapp else ''
