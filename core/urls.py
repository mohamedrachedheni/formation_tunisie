from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.AccueilView.as_view(), name='accueil'),
    path('a-propos/', views.AProposView.as_view(), name='a_propos'),
    path('faq/', views.FaqView.as_view(), name='faq'),
]
