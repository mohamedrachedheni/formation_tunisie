from django.urls import path

from . import views

app_name = 'certificates'

urlpatterns = [
    # Adresse imprimée dans le QR code : identifiant public (uuid), jamais l'id ni le numéro.
    path('verifier/<uuid:uuid>/', views.verifier, name='verifier'),
]
