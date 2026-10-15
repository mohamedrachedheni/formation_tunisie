from django import template
from django.db.models import Count, Q

from ..models import Categorie, Formation

register = template.Library()


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
