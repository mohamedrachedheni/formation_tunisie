from django.views.generic import ListView, TemplateView

from .models import EmplacementPhoto, Partenaire, QuestionFrequente, Temoignage

NOMBRE_QUESTIONS_ACCUEIL = 5


class AccueilView(TemplateView):
    template_name = 'core/accueil.html'

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte['temoignages'] = Temoignage.objects.publies()[:6]
        contexte['partenaires'] = Partenaire.objects.publies()
        questions = list(QuestionFrequente.objects.publies()[:NOMBRE_QUESTIONS_ACCUEIL + 1])
        contexte['questions'] = questions[:NOMBRE_QUESTIONS_ACCUEIL]
        contexte['autres_questions'] = len(questions) > NOMBRE_QUESTIONS_ACCUEIL
        contexte['photos'] = EmplacementPhoto.pour_page(EmplacementPhoto.Page.ACCUEIL)
        return contexte


class AProposView(TemplateView):
    template_name = 'core/a_propos.html'

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte['photos'] = EmplacementPhoto.pour_page(EmplacementPhoto.Page.A_PROPOS)
        return contexte


class FaqView(ListView):
    template_name = 'core/faq.html'
    context_object_name = 'questions'

    def get_queryset(self):
        return QuestionFrequente.objects.publies()

# La page Contact est servie par l'application `commercial` (formulaire DemandeContact) ;
# `core` ne fournit que le fragment des coordonnées (core/_coordonnees.html).
