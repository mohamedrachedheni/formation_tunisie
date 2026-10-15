"""Redimensionnement et compression des photos envoyées depuis l'administration."""

from io import BytesIO
from pathlib import PurePath

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

TAILLE_MAX_ENVOI = 10 * 1024 * 1024  # 10 Mo : au-delà, l'envoi est refusé
QUALITE_WEBP = 82


def valider_taille_image(fichier):
    if fichier.size > TAILLE_MAX_ENVOI:
        raise ValidationError(f'La photo ne doit pas dépasser {TAILLE_MAX_ENVOI // (1024 * 1024)} Mo.')


def compresser_image(fichier, largeur_max):
    """Retourne une version WebP de la photo, redressée et réduite à `largeur_max` pixels de large.

    - L'orientation enregistrée par le téléphone (EXIF) est appliquée, puis les métadonnées
      (lieu de prise de vue, appareil…) sont supprimées : ce sont des données personnelles.
    - Une image plus petite que `largeur_max` n'est jamais agrandie.
    - La transparence est conservée (logos, illustrations).
    """
    try:
        fichier.seek(0)
        with Image.open(fichier) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in ('RGB', 'RGBA'):
                image = image.convert('RGBA' if 'A' in image.getbands() or image.mode == 'P' else 'RGB')
            if image.width > largeur_max:
                hauteur = round(image.height * largeur_max / image.width)
                image = image.resize((largeur_max, hauteur), Image.Resampling.LANCZOS)
            sortie = BytesIO()
            image.save(sortie, format='WEBP', quality=QUALITE_WEBP, method=6)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as erreur:
        raise ValidationError('Le fichier envoyé n’est pas une image valide.') from erreur
    nom = PurePath(fichier.name).stem or 'photo'
    return ContentFile(sortie.getvalue(), name=f'{nom}.webp')
