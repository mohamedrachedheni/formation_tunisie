from django import template

from ..models import Formateur

register = template.Library()


@register.inclusion_tag('trainers/_equipe.html')
def equipe_formateurs(nombre=8):
    """Formateurs actifs et visibles sur le site (jamais le CV ni les coordonnées)."""
    return {'formateurs': Formateur.objects.visibles().order_by('nom', 'prenom')[:nombre]}


@register.simple_tag
def nombre_formateurs_visibles():
    return Formateur.objects.visibles().count()
