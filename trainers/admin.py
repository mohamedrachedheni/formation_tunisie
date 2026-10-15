from django.contrib import admin
from django.contrib.auth.models import Group
from django.utils import timezone

from accounts.models import Roles

from .models import Formateur


@admin.register(Formateur)
class FormateurAdmin(admin.ModelAdmin):
    list_display = ('nom_complet', 'specialite', 'telephone', 'email', 'utilisateur', 'est_actif', 'est_visible_site')
    list_display_links = ('nom_complet',)
    list_filter = ('est_actif', 'est_visible_site')
    list_select_related = ('utilisateur',)
    search_fields = ('nom', 'prenom', 'email', 'telephone', 'specialite')
    autocomplete_fields = ('utilisateur',)
    readonly_fields = ('uuid', 'date_creation', 'date_modification')
    actions = ('desactiver',)
    fieldsets = (
        ('Identité', {'fields': ('prenom', 'nom', 'specialite', 'photo', 'biographie')}),
        ('Coordonnées', {'fields': ('telephone', 'email')}),
        ('Documents', {'fields': ('cv',)}),
        ('Statut', {'fields': ('est_actif', 'est_visible_site', 'utilisateur')}),
        ('Suivi', {'classes': ('collapse',), 'fields': ('uuid', 'date_creation', 'date_modification')}),
    )

    def get_readonly_fields(self, request, obj=None):
        # Rattacher un compte suppose de pouvoir consulter les comptes (réservé à l'administration).
        champs = super().get_readonly_fields(request, obj)
        if not request.user.has_perm('accounts.view_utilisateur'):
            champs = (*champs, 'utilisateur')
        return champs

    @admin.display(description='formateur', ordering='nom')
    def nom_complet(self, obj):
        return obj.nom_complet

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Un compte lié à un formateur reçoit le rôle Formateur (utile pour l'espace formateur du niveau 3).
        # Le rôle n'est jamais retiré automatiquement : la personne peut avoir d'autres fonctions.
        if obj.utilisateur_id:
            obj.utilisateur.groups.add(Group.objects.get(name=Roles.FORMATEUR))

    @admin.action(description='Désactiver (et retirer du site)', permissions=['change'])
    def desactiver(self, request, queryset):
        # Désactivation plutôt que suppression : l'historique des sessions est conservé.
        nombre = queryset.update(est_actif=False, est_visible_site=False, date_modification=timezone.now())
        self.message_user(request, f'{nombre} formateur(s) désactivé(s).')
