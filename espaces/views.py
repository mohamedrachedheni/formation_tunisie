from pathlib import PurePath

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.text import slugify
from django.views.generic import DetailView, TemplateView, UpdateView, View

from catalog.models import DocumentFormation
from certificates.models import Certificat
from certificates.views import reponse_pdf
from enrollments.models import Inscription, Session

from .acces import EspaceCandidatMixin, EspaceFormateurMixin, candidat_de, formateur_de, peut_telecharger
from .forms import ProfilCandidatForm


class TableauView(LoginRequiredMixin, View):
    """Après la connexion : chacun est dirigé vers son espace."""

    def get(self, request):
        candidat, formateur = candidat_de(request.user), formateur_de(request.user)
        if candidat and formateur:
            return render(request, 'espaces/choix_espace.html')
        if candidat:
            return redirect('espaces:candidat')
        if formateur:
            return redirect('espaces:formateur')
        if request.user.is_staff:
            return redirect('admin:index')
        return render(request, 'espaces/aucun_espace.html')


# --- Espace candidat ------------------------------------------------------------------------

class EspaceCandidatView(EspaceCandidatMixin, TemplateView):
    template_name = 'espaces/candidat.html'

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        inscriptions = (
            self.candidat.inscriptions.select_related('session__formation', 'session__formateur')
            .order_by('-session__date_debut')
        )
        # Documents réservés : formations pour lesquelles le candidat est confirmé (ou a terminé).
        formations_suivies = inscriptions.filter(statut__in=Inscription.STATUTS_OCCUPANT_UNE_PLACE).values('session__formation')
        contexte.update({
            'candidat': self.candidat,
            'inscriptions': inscriptions,
            'documents': DocumentFormation.objects.filter(formation__in=formations_suivies).select_related('formation')
                         .order_by('formation__titre', 'titre'),
            # Seuls les documents valides sont proposés : un certificat annulé n'est plus téléchargeable.
            'certificats': Certificat.objects.filter(inscription__candidat=self.candidat, statut=Certificat.Statut.VALIDE),
        })
        return contexte


class CertificatCandidatPdfView(EspaceCandidatMixin, View):
    """Téléchargement d'un certificat par son titulaire uniquement (sinon 404)."""

    def get(self, request, uuid):
        certificat = get_object_or_404(
            Certificat, uuid=uuid, inscription__candidat=self.candidat, statut=Certificat.Statut.VALIDE,
        )
        return reponse_pdf(request, certificat)


class ProfilCandidatView(EspaceCandidatMixin, UpdateView):
    template_name = 'espaces/profil.html'
    form_class = ProfilCandidatForm
    success_url = reverse_lazy('espaces:candidat')

    def get_object(self, queryset=None):
        return self.candidat  # toujours la fiche de la personne connectée, jamais une autre

    def form_valid(self, form):
        messages.success(self.request, 'Vos coordonnées ont été mises à jour.')
        return super().form_valid(form)


# --- Espace formateur -----------------------------------------------------------------------

class EspaceFormateurView(EspaceFormateurMixin, TemplateView):
    template_name = 'espaces/formateur.html'

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        aujourd_hui = timezone.localdate()
        sessions = list(
            Session.objects.filter(formateur=self.formateur).select_related('formation')
            .avec_places_occupees().order_by('date_debut')
        )
        a_venir, en_cours, passees = [], [], []
        for session in sessions:
            if session.statut == Session.Statut.ANNULEE or session.date_fin < aujourd_hui or session.statut == Session.Statut.TERMINEE:
                passees.append(session)
            elif session.date_debut > aujourd_hui:
                a_venir.append(session)
            else:
                en_cours.append(session)
        formations = {s.formation_id for s in sessions if s.statut != Session.Statut.ANNULEE}
        contexte.update({
            'formateur': self.formateur,
            'en_cours': en_cours, 'a_venir': a_venir, 'passees': list(reversed(passees)),
            'documents': DocumentFormation.objects.filter(formation_id__in=formations).select_related('formation')
                         .order_by('formation__titre', 'titre'),
        })
        return contexte


class SessionFormateurView(EspaceFormateurMixin, DetailView):
    template_name = 'espaces/session.html'
    context_object_name = 'session'
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'

    def get_queryset(self):
        # Seulement les sessions animées par ce formateur : celle d'un collègue donne une 404.
        return Session.objects.filter(formateur=self.formateur).select_related('formation').avec_places_occupees()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        # Inscrits confirmés ou ayant terminé. Le formateur voit nom, prénom, téléphone et email ;
        # jamais la CIN, le prix ni les notes internes (le gabarit n'utilise que ces champs).
        contexte['inscrits'] = (
            self.object.inscriptions.filter(statut__in=Inscription.STATUTS_OCCUPANT_UNE_PLACE)
            .select_related('candidat').order_by('candidat__nom', 'candidat__prenom')
        )
        return contexte


# --- Téléchargement des documents (stockage privé) --------------------------------------------

def fichier_prive(request, chemin):
    """Sert un document du stockage privé après vérification des droits (voir acces.peut_telecharger).

    Le fichier est retrouvé par son nom EXACT enregistré en base : un chemin inventé (« ../… ») ne correspond
    à aucun document. Sans droit, la réponse est une 404, pour ne pas révéler l'existence du fichier.
    """
    document = DocumentFormation.objects.filter(fichier=chemin).select_related('formation').first()
    if document is None or not peut_telecharger(request.user, document):
        raise Http404('Document introuvable.')
    try:
        fichier = document.fichier.open('rb')
    except FileNotFoundError as erreur:
        raise Http404('Document introuvable.') from erreur
    nom = f'{slugify(document.titre) or "document"}{PurePath(document.fichier.name).suffix}'
    reponse = FileResponse(fichier, filename=nom)
    reponse['Cache-Control'] = 'private, no-store'
    return reponse
