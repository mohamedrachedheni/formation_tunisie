import uuid
from pathlib import PurePath

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class StockagePrive(FileSystemStorage):
    """Stockage des fichiers réservés (hors de MEDIA_ROOT, jamais servis directement par le serveur web).

    Dossier : settings.FICHIERS_PRIVES_ROOT. L'URL d'un fichier pointe vers la vue protégée
    `espaces:fichier_prive` (settings.FICHIERS_PRIVES_URL), qui vérifie les droits avant tout téléchargement.
    Les réglages sont lus à chaque utilisation (et non figés au démarrage) : les tests peuvent les modifier.
    """

    def __init__(self):
        super().__init__()

    @property
    def base_location(self):
        return str(settings.FICHIERS_PRIVES_ROOT)

    @property
    def location(self):
        return str(PurePath(self.base_location))

    @property
    def base_url(self):
        url = settings.FICHIERS_PRIVES_URL
        return url if url.endswith('/') else f'{url}/'


@deconstructible
class CheminAleatoire:
    """`upload_to` qui range le fichier dans `dossier` sous un nom aléatoire.

    Le nom d'origine n'est pas conservé : il peut contenir des données personnelles
    et rendrait l'adresse du fichier facile à deviner.
    """

    def __init__(self, dossier):
        self.dossier = dossier.strip('/')

    def __call__(self, instance, nom_fichier):
        return f'{self.dossier}/{uuid.uuid4().hex}{PurePath(nom_fichier).suffix.lower()}'

    def __eq__(self, autre):
        return isinstance(autre, CheminAleatoire) and self.dossier == autre.dossier
