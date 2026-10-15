from django.urls import path

from . import views

app_name = 'catalog'

urlpatterns = [
    path('', views.FormationListView.as_view(), name='liste'),
    path('<slug:slug>/', views.FormationDetailView.as_view(), name='detail'),
]
