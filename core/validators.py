import re

from django.core.validators import RegexValidator

# Numéro de téléphone : chiffres, espaces, points ou tirets, avec un « + » initial facultatif.
# Exemples acceptés : 71 123 456, 98-123-456, +216 98 123 456.
valider_telephone = RegexValidator(
    r'^\+?[0-9][0-9 .-]{6,18}[0-9]$',
    'Saisissez un numéro de téléphone valide (8 chiffres au minimum).',
)


def normaliser_telephone(numero):
    """Forme unique d'un numéro, pour comparer et retrouver une personne quelle que soit la saisie.

    - Les séparateurs (espaces, points, tirets) sont supprimés.
    - Un numéro tunisien saisi avec l'indicatif (+216 ou 00216) est ramené à ses 8 chiffres.
    - Un numéro étranger garde son indicatif sous la forme +XXX…
    Exemples : « +216 98 123 456 », « 00216-98.123.456 » et « 98 123 456 » donnent « 98123456 ».
    """
    if not numero:
        return ''
    chiffres = re.sub(r'[^0-9+]', '', numero.strip())
    if chiffres.startswith('00'):
        chiffres = '+' + chiffres[2:]
    if chiffres.startswith('+216') and len(chiffres) == 12:
        return chiffres[4:]
    return chiffres
