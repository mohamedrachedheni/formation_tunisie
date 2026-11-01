from decimal import Decimal, InvalidOperation

from django import template
from django.db.models import Count, Q
from django.template.defaultfilters import floatformat

from ..models import Categorie, Formation

register = template.Library()


@register.filter
def montant(valeur):
    """Montant affiché sans zéros inutiles après la virgule (pages publiques uniquement).

    Les prix sont stockés avec 3 décimales (millimes) : 850.000 → « 850 », 1250.500 → « 1 250,5 »,
    1250.375 → « 1 250,375 ». L'administration Django conserve l'affichage complet.
    """
    try:
        nombre = Decimal(str(valeur))
    except (InvalidOperation, TypeError, ValueError):
        return valeur
    decimales = max(-nombre.normalize().as_tuple().exponent, 0)
    return floatformat(nombre, f'{decimales}g')


def categories_visibles():
    # Catégories actives ayant au moins une formation publiée.
    return (
        Categorie.objects.filter(est_active=True)
        .annotate(nb_publiees=Count('formations', filter=Q(formations__est_publiee=True)))
        .filter(nb_publiees__gt=0)
    )


@register.simple_tag
def domaines_de_formation():
    """Catégories visibles, avec leur nombre de formations publiées (`nb_publiees`)."""
    return categories_visibles()


@register.simple_tag
def nombre_formations_publiees():
    return Formation.objects.publiees().count()


@register.inclusion_tag('catalog/_formations_a_la_une.html')
def formations_a_la_une(nombre=6):
    """Formations mises « à la une » ; à défaut, les dernières formations publiées."""
    formations = Formation.objects.publiees().select_related('categorie')
    a_la_une = list(formations.filter(est_a_la_une=True).order_by('titre')[:nombre])
    return {'formations': a_la_une or list(formations.order_by('-date_creation')[:nombre])}
