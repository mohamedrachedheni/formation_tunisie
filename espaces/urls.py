from django.urls import path

from . import views

app_name = 'espaces'

urlpatterns = [
    path('', views.TableauView.as_view(), name='tableau'),
    path('candidat/', views.EspaceCandidatView.as_view(), name='candidat'),
    path('candidat/profil/', views.ProfilCandidatView.as_view(), name='profil'),
    path('candidat/certificats/<uuid:uuid>/pdf/', views.CertificatCandidatPdfView.as_view(), name='certificat_pdf'),
    path('formateur/', views.EspaceFormateurView.as_view(), name='formateur'),
    # Identifiant public (uuid) de la session : jamais l'id numérique.
    path('formateur/sessions/<uuid:uuid>/', views.SessionFormateurView.as_view(), name='session'),
    # Documents du stockage privé (settings.FICHIERS_PRIVES_URL = '/espace/fichiers/').
    path('fichiers/<path:chemin>', views.fichier_prive, name='fichier_prive'),
]
