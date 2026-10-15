from django.db import models


class Gouvernorat(models.TextChoices):
    """Les 24 gouvernorats de Tunisie."""

    ARIANA = 'ariana', 'Ariana'
    BEJA = 'beja', 'Béja'
    BEN_AROUS = 'ben_arous', 'Ben Arous'
    BIZERTE = 'bizerte', 'Bizerte'
    GABES = 'gabes', 'Gabès'
    GAFSA = 'gafsa', 'Gafsa'
    JENDOUBA = 'jendouba', 'Jendouba'
    KAIROUAN = 'kairouan', 'Kairouan'
    KASSERINE = 'kasserine', 'Kasserine'
    KEBILI = 'kebili', 'Kébili'
    LE_KEF = 'le_kef', 'Le Kef'
    MAHDIA = 'mahdia', 'Mahdia'
    LA_MANOUBA = 'la_manouba', 'La Manouba'
    MEDENINE = 'medenine', 'Médenine'
    MONASTIR = 'monastir', 'Monastir'
    NABEUL = 'nabeul', 'Nabeul'
    SFAX = 'sfax', 'Sfax'
    SIDI_BOUZID = 'sidi_bouzid', 'Sidi Bouzid'
    SILIANA = 'siliana', 'Siliana'
    SOUSSE = 'sousse', 'Sousse'
    TATAOUINE = 'tataouine', 'Tataouine'
    TOZEUR = 'tozeur', 'Tozeur'
    TUNIS = 'tunis', 'Tunis'
    ZAGHOUAN = 'zaghouan', 'Zaghouan'
