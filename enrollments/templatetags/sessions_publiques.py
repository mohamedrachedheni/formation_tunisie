from django import template

from ..views import lien_whatsapp_session, sessions_visibles

register = template.Library()


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
