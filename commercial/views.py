from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import FormView

from catalog.models import Formation

from .forms import DemandeContactForm
from .models import DemandeContact

MESSAGE_SUCCES = 'Merci, votre demande a bien été envoyée. Nous vous répondrons dans les meilleurs délais.'


class ContactView(FormView):
    template_name = 'commercial/contact.html'
    form_class = DemandeContactForm
    success_url = reverse_lazy('commercial:contact')

    def get_initial(self):
        initial = super().get_initial()
        # Préremplissage depuis une fiche formation : /contact/?formation=<slug>.
        # Un slug inconnu ou non publié est simplement ignoré.
        slug = self.request.GET.get('formation')
        if slug:
            formation = Formation.objects.publiees().filter(slug=slug).first()
            if formation:
                initial['formation'] = formation.uuid
                initial['message'] = f'Bonjour, je souhaite avoir des informations sur la formation « {formation.titre} ».'
        return initial

    def form_valid(self, form):
        # Un robot qui remplit le champ piège reçoit la même réponse qu'un visiteur,
        # pour ne pas lui révéler la protection, mais rien n'est enregistré.
        if not form.est_spam():
            demande = form.save(commit=False)
            demande.source = DemandeContact.Source.FORMULAIRE
            demande.statut = DemandeContact.Statut.NOUVELLE
            demande.save()
        messages.success(self.request, MESSAGE_SUCCES)
        return super().form_valid(form)
