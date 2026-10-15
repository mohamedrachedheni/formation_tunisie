from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import UtilisateurChangeForm, UtilisateurCreationForm
from .models import Utilisateur


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    form = UtilisateurChangeForm
    add_form = UtilisateurCreationForm
    list_display = ('email', 'first_name', 'last_name', 'telephone', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')
    search_fields = ('email', 'username', 'first_name', 'last_name', 'telephone')
    ordering = ('email',)
    readonly_fields = ('uuid', 'last_login', 'date_joined')

    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Informations personnelles', {'fields': ('first_name', 'last_name', 'telephone')}),
        ('Rôles et permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Suivi', {'fields': ('uuid', 'last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'first_name', 'last_name', 'password1', 'password2'),
        }),
    )
