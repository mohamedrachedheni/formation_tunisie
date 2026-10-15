from django.contrib import admin

from .models import ParametresCentre


@admin.register(ParametresCentre)
class ParametresCentreAdmin(admin.ModelAdmin):
    list_display = ('nom', 'telephone', 'email', 'date_modification')
    readonly_fields = ('uuid', 'date_creation', 'date_modification')
    fieldsets = (
        ('Identité', {'fields': ('nom', 'slogan', 'presentation', 'logo', 'matricule_fiscal')}),
        ('Coordonnées', {'fields': ('adresse', 'ville', 'telephone', 'whatsapp', 'email')}),
        ('Réseaux sociaux', {'fields': ('facebook', 'instagram', 'linkedin')}),
        ('Suivi', {'fields': ('uuid', 'date_creation', 'date_modification')}),
    )

    # Une seule ligne de paramètres : pas d'ajout si elle existe déjà, jamais de suppression.
    def has_add_permission(self, request):
        return super().has_add_permission(request) and not ParametresCentre.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
