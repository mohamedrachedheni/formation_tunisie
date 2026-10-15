from django.urls import path

from . import views

app_name = 'commercial'

urlpatterns = [
    path('contact/', views.ContactView.as_view(), name='contact'),
]
