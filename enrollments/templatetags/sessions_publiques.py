from django import template

from ..models import Inscription
from ..views import lien_whatsapp_session, sessions_visibles

register = template.Library()


@register.inclusion_tag('enrollments/_prochaines_sessions.html', takes_context=True)
def prochaines_sessions(context, nombre=3):
    """Prochaines sessions ouvertes, toutes formations confondues (page d'accueil)."""
    centre = context.get('centre')
    sessions = list(sessions_visibles().order_by('date_debut')[:nombre])
    for session in sessions:
        session.lien_whatsapp = lien_whatsapp_session(session, centre) if centre else ''
    return {'sessions': sessions}


@register.simple_tag
def nombre_sessions_ouvertes():
    return sessions_visibles().count()


@register.simple_tag
def nombre_stagiaires_formes():
    # Personnes ayant terminé au moins une formation (chaque personne comptée une fois).
    return Inscription.objects.filter(statut=Inscription.Statut.TERMINEE).values('candidat').distinct().count()


@register.inclusion_tag('enrollments/_sessions_formation.html', takes_context=True)
def sessions_de_la_formation(context, formation):
    """Sessions ouvertes d'une formation, pour la fiche formation (catalog).

    Fournie par `enrollments` sous forme de balise de gabarit : `catalog` n'importe ainsi
    aucun code d'`enrollments` (dépendance limitée à l'affichage).
    """
    centre = context.get('centre')
    sessions = list(sessions_visibles().filter(formation=formation).order_by('date_debut'))
    for session in sessions:
        session.lien_whatsapp = lien_whatsapp_session(session, centre) if centre else ''
    return {'sessions': sessions, 'formation': formation}
