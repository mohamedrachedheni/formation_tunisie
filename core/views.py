from django.views.generic import TemplateView


class AccueilView(TemplateView):
    template_name = 'core/accueil.html'


class AProposView(TemplateView):
    template_name = 'core/a_propos.html'

# La page Contact est servie par l'application `commercial` (formulaire DemandeContact) ;
# `core` ne fournit que le fragment des coordonnées (core/_coordonnees.html).
