from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import cache_control

from .models import Certificat
from .pdf import generer_pdf


@cache_control(no_store=True)
def verifier(request, uuid):
    """Page publique de vérification (adresse du QR code).

    Données minimales : numéro, titulaire, formation, dates, type et statut. Jamais la CIN,
    les coordonnées, le prix, le résultat détaillé ni le motif d'une annulation.
    L'uuid n'est pas devinable : on ne peut pas parcourir les certificats des autres.
    """
    certificat = get_object_or_404(Certificat, uuid=uuid)
    return render(request, 'certificates/verifier.html', {'certificat': certificat})


def reponse_pdf(request, certificat):
    """Réponse de téléchargement du PDF. Les droits sont vérifiés par la vue appelante."""
    url_verification = request.build_absolute_uri(certificat.get_absolute_url())
    reponse = HttpResponse(generer_pdf(certificat, url_verification), content_type='application/pdf')
    reponse['Content-Disposition'] = f'attachment; filename="{certificat.numero}.pdf"'
    reponse['Cache-Control'] = 'private, no-store'
    return reponse
