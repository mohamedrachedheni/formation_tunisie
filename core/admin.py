from django.contrib import admin, messages
from django.utils import timezone

from .models import ParametresCentre, Partenaire, QuestionFrequente, Temoignage


@admin.register(ParametresCentre)
class ParametresCentreAdmin(admin.ModelAdmin):
    list_display = ('nom', 'telephone', 'email', 'date_modification')
    readonly_fields = ('uuid', 'date_creation', 'date_modification')
    fieldsets = (
        ('Identité', {'fields': ('nom', 'slogan', 'presentation', 'logo', 'image_accueil', 'matricule_fiscal')}),
        ('Coordonnées', {'fields': ('adresse', 'ville', 'telephone', 'whatsapp', 'email')}),
        ('Réseaux sociaux', {'fields': ('facebook', 'instagram', 'linkedin')}),
        ('Suivi', {'fields': ('uuid', 'date_creation', 'date_modification')}),
    )

    # Une seule ligne de paramètres : pas d'ajout si elle existe déjà, jamais de suppression.
    def has_add_permission(self, request):
        return super().has_add_permission(request) and not ParametresCentre.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class ContenuOrdonneAdmin(admin.ModelAdmin):
    """Contenus du site affichés dans un ordre choisi, publiables depuis la liste."""

    list_editable = ('ordre', 'est_publie')
    list_filter = ('est_publie',)
    readonly_fields = ('uuid', 'date_creation', 'date_modification')
    actions = ('publier', 'retirer_du_site')

    @admin.action(description='Publier sur le site', permissions=['change'])
    def publier(self, request, queryset):
        # Les témoignages sans accord de la personne ne sont jamais publiés (contrainte en base).
        if queryset.model is Temoignage:
            refuses = queryset.filter(consentement_obtenu=False).count()
            queryset = queryset.filter(consentement_obtenu=True)
            if refuses:
                self.message_user(request, f'{refuses} témoignage(s) non publié(s) : accord de la personne manquant.', messages.WARNING)
        nombre = queryset.update(est_publie=True, date_modification=timezone.now())
        self.message_user(request, f'{nombre} élément(s) publié(s).')

    @admin.action(description='Retirer du site', permissions=['change'])
    def retirer_du_site(self, request, queryset):
        nombre = queryset.update(est_publie=False, date_modification=timezone.now())
        self.message_user(request, f'{nombre} élément(s) retiré(s) du site.')


@admin.register(Temoignage)
class TemoignageAdmin(ContenuOrdonneAdmin):
    list_display = ('nom', 'fonction', 'formation_suivie', 'note', 'consentement_obtenu', 'ordre', 'est_publie')
    list_filter = ('est_publie', 'consentement_obtenu', 'note')
    search_fields = ('nom', 'fonction', 'formation_suivie', 'texte')
    fieldsets = (
        (None, {'fields': ('nom', 'fonction', 'formation_suivie', 'photo')}),
        ('Témoignage', {'fields': ('texte', 'note')}),
        ('Publication', {'fields': ('consentement_obtenu', 'est_publie', 'ordre')}),
        ('Suivi', {'classes': ('collapse',), 'fields': ('uuid', 'date_creation', 'date_modification')}),
    )


@admin.register(Partenaire)
class PartenaireAdmin(ContenuOrdonneAdmin):
    list_display = ('nom', 'site_web', 'ordre', 'est_publie')
    search_fields = ('nom',)
    fields = ('nom', 'logo', 'site_web', 'est_publie', 'ordre', 'uuid', 'date_creation', 'date_modification')


@admin.register(QuestionFrequente)
class QuestionFrequenteAdmin(ContenuOrdonneAdmin):
    list_display = ('question', 'ordre', 'est_publie')
    search_fields = ('question', 'reponse')
    fields = ('question', 'reponse', 'est_publie', 'ordre', 'uuid', 'date_creation', 'date_modification')
