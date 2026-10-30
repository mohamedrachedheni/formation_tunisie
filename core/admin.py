from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html

from .models import EmplacementPhoto, ParametresCentre, Partenaire, QuestionFrequente, Temoignage


@admin.register(ParametresCentre)
class ParametresCentreAdmin(admin.ModelAdmin):
    list_display = ('nom', 'telephone', 'email', 'date_modification')
    readonly_fields = ('uuid', 'date_creation', 'date_modification')
    fieldsets = (
        ('Identité', {'fields': ('nom', 'slogan', 'presentation', 'logo', 'matricule_fiscal')}),
        ('Coordonnées', {'fields': ('adresse', 'ville', 'telephone', 'whatsapp', 'email')}),
        ('Réseaux sociaux', {'fields': ('facebook', 'instagram', 'linkedin')}),
        ('Certificats', {'fields': ('signataire_nom', 'signataire_fonction', 'signature')}),
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


@admin.register(EmplacementPhoto)
class EmplacementPhotoAdmin(admin.ModelAdmin):
    """Changement des photos du site. Réservé à l'Administrateur (permission change_emplacementphoto)."""

    list_display = ('apercu', 'libelle', 'page', 'format_conseille', 'a_une_photo')
    list_display_links = ('apercu', 'libelle')
    list_filter = ('page',)
    readonly_fields = ('libelle', 'page', 'cle', 'format_conseille', 'apercu_grand', 'date_modification')
    fields = ('libelle', 'page', 'format_conseille', 'apercu_grand', 'fichier', 'texte_alternatif', 'cle', 'date_modification')

    # Les emplacements correspondent à des endroits précis des pages : ils sont créés par migration,
    # jamais ajoutés ni supprimés à la main (pas même par le superutilisateur).
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='aperçu')
    def apercu(self, obj):
        if not obj.fichier:
            return '—'
        return format_html('<img src="{}" alt="" style="height:48px;width:auto;border-radius:4px">', obj.fichier.url)

    @admin.display(description='photo actuelle')
    def apercu_grand(self, obj):
        if not obj.fichier:
            return 'Aucune photo : la page affiche son fond par défaut.'
        return format_html('<img src="{}" alt="" style="max-width:480px;height:auto;border-radius:6px">', obj.fichier.url)

    @admin.display(description='photo', boolean=True)
    def a_une_photo(self, obj):
        return bool(obj.fichier)
