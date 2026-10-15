from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.views.generic import DetailView, ListView

from core.models import ParametresCentre

from .models import Categorie, DocumentFormation, Formation


class FormationListView(ListView):
    template_name = 'catalog/formation_liste.html'
    context_object_name = 'formations'
    paginate_by = 12

    def get_queryset(self):
        formations = Formation.objects.publiees().select_related('categorie').order_by('categorie__ordre', 'titre')
        self.categorie_active = None
        slug_categorie = self.request.GET.get('categorie')
        if slug_categorie:
            # Une catégorie inconnue ou inactive renvoie une page 404 plutôt qu'une liste vide trompeuse.
            self.categorie_active = get_object_or_404(Categorie, slug=slug_categorie, est_active=True)
            formations = formations.filter(categorie=self.categorie_active)
        return formations

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        # Seules les catégories ayant au moins une formation visible sont proposées comme filtre.
        contexte['categories'] = (
            Categorie.objects.filter(est_active=True)
            .annotate(nb_publiees=Count('formations', filter=Q(formations__est_publiee=True)))
            .filter(nb_publiees__gt=0)
        )
        contexte['categorie_active'] = self.categorie_active
        return contexte


class FormationDetailView(DetailView):
    template_name = 'catalog/formation_detail.html'
    context_object_name = 'formation'

    def get_queryset(self):
        # Une formation non publiée (ou de catégorie inactive) n'existe pas pour le public : 404.
        return Formation.objects.publiees().select_related('categorie').prefetch_related(
            'modules',
            Prefetch('documents', queryset=DocumentFormation.objects.filter(est_public=True), to_attr='documents_publics'),
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        centre = ParametresCentre.obtenir()
        if centre and centre.whatsapp:
            message = f'Bonjour, je souhaite avoir des informations sur la formation « {self.object.titre} ».'
            contexte['lien_whatsapp_formation'] = centre.lien_whatsapp_avec_message(message)
        return contexte
