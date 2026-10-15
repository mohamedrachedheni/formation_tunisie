from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import FormView, ListView, TemplateView

from core.models import ParametresCentre

from . import services
from .forms import PreInscriptionForm
from .models import Session

MESSAGE_SUCCES = (
    'Merci, votre demande d’inscription a bien été enregistrée. '
    'Le centre vous contactera pour la confirmer.'
)


def message_whatsapp_session(session):
    return (
        f'Bonjour, je souhaite m’inscrire à la session {session.code} '
        f'« {session.formation.titre} » du {session.date_debut:%d/%m/%Y}.'
    )


def lien_whatsapp_session(session, centre=None):
    centre = centre if centre is not None else ParametresCentre.obtenir()
    return centre.lien_whatsapp_avec_message(message_whatsapp_session(session)) if centre else ''


def sessions_visibles():
    return Session.objects.visibles().avec_places_occupees().select_related('formation', 'formateur')


class SessionListView(ListView):
    template_name = 'enrollments/session_liste.html'
    context_object_name = 'sessions'
    paginate_by = 20

    def get_queryset(self):
        return sessions_visibles().order_by('date_debut', 'formation__titre')

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        centre = ParametresCentre.obtenir()
        for session in contexte['sessions']:
            session.lien_whatsapp = lien_whatsapp_session(session, centre)
        return contexte


class SessionVisibleMixin:
    """Charge la session depuis son uuid ; 404 si elle n'est pas visible sur le site."""

    def dispatch(self, request, *args, **kwargs):
        self.session = get_object_or_404(sessions_visibles(), uuid=kwargs['uuid'])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte['session'] = self.session
        contexte['lien_whatsapp_session'] = lien_whatsapp_session(self.session)
        return contexte


class PreInscriptionView(SessionVisibleMixin, FormView):
    template_name = 'enrollments/pre_inscription.html'
    form_class = PreInscriptionForm

    def form_valid(self, form):
        # Un robot qui remplit le champ piège reçoit la même réponse qu'un visiteur, sans enregistrement.
        if not form.est_spam():
            donnees = {champ: form.cleaned_data.get(champ) for champ in PreInscriptionForm.Meta.fields}
            try:
                services.pre_inscrire(self.session, donnees, message=form.cleaned_data.get('message', ''))
            except services.InscriptionImpossible as erreur:
                form.add_error(None, erreur.message)
                return self.form_invalid(form)
        # Même message si le candidat était déjà inscrit : on ne révèle pas qui est inscrit à quelle session.
        messages.success(self.request, MESSAGE_SUCCES)
        return redirect('enrollments:merci', uuid=self.session.uuid)


class PreInscriptionMerciView(SessionVisibleMixin, TemplateView):
    template_name = 'enrollments/pre_inscription_merci.html'
