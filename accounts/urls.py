from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('connexion/', views.ConnexionView.as_view(), name='connexion'),
    path('deconnexion/', views.DeconnexionView.as_view(), name='deconnexion'),
    path('mot-de-passe-oublie/', views.MotDePasseOublieView.as_view(), name='mot_de_passe_oublie'),
    path('mot-de-passe-oublie/envoye/', views.MotDePasseOublieEnvoyeView.as_view(), name='mot_de_passe_oublie_envoye'),
    # uidb64 = uuid du compte encodé (jamais l'id numérique) ; token = jeton signé à usage unique.
    path('reinitialiser/<uidb64>/<token>/', views.ReinitialisationView.as_view(), name='reinitialisation'),
    path('reinitialiser/termine/', views.ReinitialisationTermineeView.as_view(), name='reinitialisation_terminee'),
    path('activer/<uidb64>/<token>/', views.ActivationView.as_view(), name='activation'),
]
