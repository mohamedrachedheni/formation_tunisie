from .models import ParametresCentre


def parametres_centre(request):
    """Rend les paramètres du centre disponibles dans tous les gabarits (variable `centre`)."""
    return {'centre': ParametresCentre.obtenir()}
