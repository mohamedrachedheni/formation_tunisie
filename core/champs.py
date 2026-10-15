"""Champ image compressé automatiquement, et suppression des fichiers remplacés."""

from django.db import models, transaction

from .images import compresser_image, valider_taille_image


class ImageCompresseeField(models.ImageField):
    """ImageField dont chaque nouvelle image est redressée, réduite et convertie en WebP à l'enregistrement.

    - `largeur_max` : largeur maximale en pixels (l'image n'est jamais agrandie) ;
    - ou `champ_largeur` : nom d'un attribut du modèle donnant cette largeur (une valeur par ligne).
    La taille de l'envoi est limitée (voir core.images.valider_taille_image).
    """

    def __init__(self, *args, largeur_max=1920, champ_largeur=None, **kwargs):
        self.largeur_max = largeur_max
        self.champ_largeur = champ_largeur
        validateurs = list(kwargs.pop('validators', []))
        if valider_taille_image not in validateurs:
            validateurs.append(valider_taille_image)
        super().__init__(*args, validators=validateurs, **kwargs)

    def deconstruct(self):
        nom, chemin, args, kwargs = super().deconstruct()
        kwargs['largeur_max'] = self.largeur_max
        if self.champ_largeur:
            kwargs['champ_largeur'] = self.champ_largeur
        # Le validateur de taille est toujours ajouté par __init__ : inutile de l'écrire dans les migrations.
        autres = [v for v in kwargs.pop('validators', []) if v is not valider_taille_image]
        if autres:
            kwargs['validators'] = autres
        return nom, chemin, args, kwargs

    def largeur_pour(self, instance):
        return getattr(instance, self.champ_largeur) if self.champ_largeur else self.largeur_max

    def pre_save(self, instance, add):
        fichier = getattr(instance, self.attname)
        # Nouvelle image envoyée (pas encore enregistrée sur le disque) : on enregistre sa version compressée.
        if fichier and not fichier._committed:
            image = compresser_image(fichier, self.largeur_pour(instance))
            fichier.save(image.name, image, save=False)
        return fichier


class SuppressionFichiersRemplacesMixin:
    """Supprime du disque l'ancienne image d'un ImageCompresseeField quand elle est remplacée ou retirée.

    L'ancien fichier n'est plus utilisé nulle part : le supprimer évite d'encombrer l'espace disque.
    La suppression a lieu après validation de la transaction (jamais si l'enregistrement échoue).
    """

    @classmethod
    def _champs_images_compressees(cls):
        return [champ for champ in cls._meta.concrete_fields if isinstance(champ, ImageCompresseeField)]

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._fichiers_initiaux = {
            champ.attname: getattr(instance, champ.attname).name
            for champ in cls._champs_images_compressees() if champ.attname in field_names
        }
        return instance

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        initiaux = getattr(self, '_fichiers_initiaux', {})
        for champ in self._champs_images_compressees():
            ancien = initiaux.get(champ.attname)
            actuel = getattr(self, champ.attname).name
            if ancien and ancien != actuel:
                transaction.on_commit(lambda stockage=champ.storage, nom=ancien: stockage.delete(nom))
            initiaux[champ.attname] = actuel
        self._fichiers_initiaux = initiaux
