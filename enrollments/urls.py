from django.urls import path

from . import views

app_name = 'enrollments'

urlpatterns = [
    path('', views.SessionListView.as_view(), name='liste'),
    # Identifiant public (uuid) dans l'adresse : jamais l'id numérique.
    path('<uuid:uuid>/inscription/', views.PreInscriptionView.as_view(), name='inscription'),
    path('<uuid:uuid>/inscription/merci/', views.PreInscriptionMerciView.as_view(), name='merci'),
]
