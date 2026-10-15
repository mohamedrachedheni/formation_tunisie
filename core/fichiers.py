import uuid
from pathlib import PurePath

from django.utils.deconstruct import deconstructible


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
