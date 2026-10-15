import uuid
from urllib.parse import quote

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .champs import ImageCompresseeField, SuppressionFichiersRemplacesMixin
from .fichiers import CheminAleatoire


class ModeleDeBase(models.Model):
    """Modèle abstrait dont héritent tous les modèles métier du projet."""

    # Identifiant public : seul identifiant utilisé dans les URL, vues et formulaires.
    # La clé primaire numérique (id) reste interne à la base de données.
    uuid = models.UUIDField('identifiant public', default=uuid.uuid4, unique=True, editable=False)
    date_creation = models.DateTimeField('date de création', auto_now_add=True)
    date_modification = models.DateTimeField('date de modification', auto_now=True)

    class Meta:
        abstract = True


class ParametresCentre(SuppressionFichiersRemplacesMixin, ModeleDeBase):
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
    # Logo affiché dans l'en-tête (36 px de haut) : 512 px de large suffisent, y compris sur écran haute densité.
    logo = ImageCompresseeField(upload_to=CheminAleatoire('centre'), blank=True, largeur_max=512)
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

    def lien_whatsapp_avec_message(self, message):
        """Lien WhatsApp avec un message prérempli, ou chaîne vide si aucun numéro n'est saisi."""
        return f'{self.lien_whatsapp}?text={quote(message)}' if self.whatsapp else ''


# --- Contenus du site vitrine (gérés depuis l'administration) --------------------------------

class ContenuPublieQuerySet(models.QuerySet):
    def publies(self):
        return self.filter(est_publie=True)


class Temoignage(SuppressionFichiersRemplacesMixin, ModeleDeBase):
    """Avis d'un ancien stagiaire ou d'une entreprise, affiché sur la page d'accueil."""

    nom = models.CharField('nom affiché', max_length=100, help_text='Par exemple « Amira B. » : évitez le nom complet si la personne le préfère.')
    fonction = models.CharField(max_length=150, blank=True, help_text='Métier ou entreprise, par exemple « Développeuse web ».')
    formation_suivie = models.CharField('formation suivie', max_length=200, blank=True)
    texte = models.TextField('témoignage', max_length=800)
    note = models.PositiveSmallIntegerField('note sur 5', null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    # Photo affichée en vignette ronde de 48 px.
    photo = ImageCompresseeField(upload_to=CheminAleatoire('temoignages'), blank=True, largeur_max=200)
    # Un témoignage est une donnée personnelle : il n'est publié qu'avec l'accord de la personne.
    consentement_obtenu = models.BooleanField(
        'accord de la personne obtenu', default=False,
        help_text='Obligatoire pour publier : la personne a accepté la diffusion de son témoignage sur le site.',
    )
    est_publie = models.BooleanField('publié', default=False)
    ordre = models.PositiveSmallIntegerField('ordre d’affichage', default=0)

    objects = ContenuPublieQuerySet.as_manager()

    class Meta:
        verbose_name = 'témoignage'
        verbose_name_plural = 'témoignages'
        ordering = ['ordre', '-date_creation']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(note__isnull=True) | models.Q(note__gte=1, note__lte=5), name='temoignage_note_1_a_5',
            ),
            models.CheckConstraint(
                condition=~models.Q(est_publie=True, consentement_obtenu=False), name='temoignage_publie_avec_consentement',
            ),
        ]

    def __str__(self):
        return f'{self.nom} — {self.texte[:40]}'

    def clean(self):
        super().clean()
        if self.est_publie and not self.consentement_obtenu:
            raise ValidationError({'est_publie': 'Un témoignage ne peut être publié qu’avec l’accord de la personne.'})


class Partenaire(SuppressionFichiersRemplacesMixin, ModeleDeBase):
    """Entreprise ou organisme partenaire, dont le logo est affiché sur la page d'accueil."""

    nom = models.CharField(max_length=150, unique=True)
    # Logo affiché sur 60 px de haut (160 px de large au plus) ; la transparence est conservée.
    logo = ImageCompresseeField(upload_to=CheminAleatoire('partenaires'), largeur_max=400, help_text='Logo sur fond transparent ou blanc, utilisé avec l’accord du partenaire.')
    site_web = models.URLField('site web', blank=True)
    est_publie = models.BooleanField('publié', default=True)
    ordre = models.PositiveSmallIntegerField('ordre d’affichage', default=0)

    objects = ContenuPublieQuerySet.as_manager()

    class Meta:
        verbose_name = 'partenaire'
        verbose_name_plural = 'partenaires'
        ordering = ['ordre', 'nom']

    def __str__(self):
        return self.nom


class QuestionFrequente(ModeleDeBase):
    """Question-réponse de la FAQ."""

    question = models.CharField(max_length=255, unique=True)
    reponse = models.TextField('réponse')
    est_publie = models.BooleanField('publiée', default=True)
    ordre = models.PositiveSmallIntegerField('ordre d’affichage', default=0)

    objects = ContenuPublieQuerySet.as_manager()

    class Meta:
        verbose_name = 'question fréquente'
        verbose_name_plural = 'questions fréquentes (FAQ)'
        ordering = ['ordre', 'question']

    def __str__(self):
        return self.question


# --- Emplacements photo ---------------------------------------------------------------------

class EmplacementPhoto(SuppressionFichiersRemplacesMixin, ModeleDeBase):
    """Emplacement réservé à une photo sur une page du site.

    Les emplacements sont créés par migration (ils correspondent à des endroits précis des gabarits) :
    dans l'administration, on ne peut ni en ajouter ni en supprimer, seulement changer la photo.
    Les gabarits les retrouvent par leur `cle`, qui ne change jamais.
    """

    class Page(models.TextChoices):
        ACCUEIL = 'accueil', 'Accueil'
        A_PROPOS = 'a_propos', 'À propos'

    cle = models.CharField('clé', max_length=50, unique=True, editable=False)
    page = models.CharField(max_length=20, choices=Page.choices, editable=False)
    libelle = models.CharField('emplacement', max_length=150, editable=False)
    format_conseille = models.CharField('format conseillé', max_length=100, blank=True, editable=False)
    # Largeur maximale après redimensionnement automatique (en pixels).
    largeur_max = models.PositiveIntegerField('largeur maximale', default=1920, editable=False)
    # Largeur propre à chaque emplacement (champ largeur_max ci-dessus).
    fichier = ImageCompresseeField(
        'photo', upload_to=CheminAleatoire('emplacements'), blank=True, champ_largeur='largeur_max',
        help_text='JPEG, PNG ou WebP, 10 Mo au plus. La photo est automatiquement redimensionnée et compressée.',
    )
    texte_alternatif = models.CharField(
        'description de la photo', max_length=200, blank=True,
        help_text='Décrit la photo pour les personnes malvoyantes et pour Google (ex. « Stagiaires en atelier de programmation »).',
    )

    class Meta:
        verbose_name = 'emplacement photo'
        verbose_name_plural = 'emplacements photo'
        ordering = ['page', 'cle']
        constraints = [
            # Toute photo publiée doit être décrite (accessibilité, référencement).
            models.CheckConstraint(
                condition=models.Q(fichier='') | ~models.Q(texte_alternatif=''), name='emplacement_photo_decrite',
            ),
        ]

    def __str__(self):
        return self.libelle

    @classmethod
    def pour_page(cls, page):
        """Dictionnaire {clé: emplacement} des emplacements d'une page (une seule requête)."""
        return {emplacement.cle: emplacement for emplacement in cls.objects.filter(page=page)}

    def clean(self):
        super().clean()
        if self.fichier and not self.texte_alternatif.strip():
            raise ValidationError({'texte_alternatif': 'Décrivez la photo en quelques mots.'})
