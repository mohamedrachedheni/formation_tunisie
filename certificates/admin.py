from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from enrollments.admin import InscriptionAdmin
from enrollments.models import Inscription

from . import services
from .models import Certificat
from .views import reponse_pdf


@admin.register(Certificat)
class CertificatAdmin(admin.ModelAdmin):
    list_display = ('numero', 'titulaire', 'formation_titre', 'type', 'statut', 'date_delivrance')
    list_filter = ('statut', 'type')
    search_fields = ('numero', 'titulaire', 'formation_titre')
    list_select_related = ('inscription',)
    actions = ('mettre_a_jour', 'annuler')
    fieldsets = (
        ('Document', {'fields': ('numero', 'type', 'statut', 'date_delivrance', 'delivre_par', 'liens')}),
        ('Contenu imprimé', {'fields': ('titulaire', 'formation_titre', 'duree_heures', 'date_debut', 'date_fin',
                                        'signataire_nom', 'signataire_fonction')}),
        ('Annulation', {'fields': ('motif_annulation', 'date_annulation')}),
        ('Suivi', {'classes': ('collapse',), 'fields': ('inscription', 'uuid', 'date_creation', 'date_modification')}),
    )

    # Un certificat n'est créé, corrigé ou annulé que par les règles métier (actions) :
    # jamais d'ajout, de modification directe ni de suppression, même pour un superutilisateur.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_delivrer_permission(self, request):
        return request.user.has_perm('certificates.delivrer_certificat')

    def has_annuler_permission(self, request):
        return request.user.has_perm('certificates.annuler_certificat')

    def get_readonly_fields(self, request, obj=None):
        return [champ for groupe in self.fieldsets for champ in groupe[1]['fields']]

    @admin.display(description='document')
    def liens(self, obj):
        return format_html(
            '<a class="button" href="{}">Télécharger le PDF</a> &nbsp; <a href="{}" target="_blank" rel="noopener">Page de vérification</a>',
            reverse('admin:certificates_certificat_pdf', args=[obj.pk]), obj.get_absolute_url(),
        )

    def get_urls(self):
        return [
            path('<path:object_id>/pdf/', self.admin_site.admin_view(self.telecharger_pdf), name='certificates_certificat_pdf'),
            *super().get_urls(),
        ]

    def telecharger_pdf(self, request, object_id):
        if not self.has_view_permission(request):
            raise PermissionDenied
        return reponse_pdf(request, get_object_or_404(Certificat, pk=object_id))

    @admin.action(description='Mettre à jour depuis l’inscription (correction)', permissions=['delivrer'])
    def mettre_a_jour(self, request, queryset):
        for certificat in queryset:
            try:
                services.mettre_a_jour(certificat)
            except services.CertificatImpossible as erreur:
                self.message_user(request, erreur.message, messages.ERROR)
            else:
                self.message_user(request, f'{certificat.numero} mis à jour.', messages.SUCCESS)

    @admin.action(description='Annuler', permissions=['annuler'])
    def annuler(self, request, queryset):
        # Page intermédiaire : le motif est obligatoire et l'annulation doit être confirmée.
        motif = request.POST.get('motif', '').strip()
        if 'confirmer' in request.POST and motif:
            for certificat in queryset:
                try:
                    services.annuler(certificat, motif)
                except services.CertificatImpossible as erreur:
                    self.message_user(request, erreur.message, messages.ERROR)
                else:
                    self.message_user(request, f'{certificat.numero} annulé.', messages.SUCCESS)
            return None
        if 'confirmer' in request.POST:
            self.message_user(request, 'Le motif d’annulation est obligatoire.', messages.ERROR)
        return TemplateResponse(request, 'certificates/admin/annuler.html', {
            **self.admin_site.each_context(request),
            'title': 'Annuler des certificats',
            'opts': self.model._meta,
            'certificats': queryset,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        })


# --- Délivrance depuis les inscriptions -----------------------------------------------------

# L'administration des inscriptions est définie dans « enrollments », qui ne connaît pas les certificats
# (ordre des dépendances). L'action de délivrance est donc ajoutée ici, en remplaçant l'enregistrement
# d'origine par une version étendue.
admin.site.unregister(Inscription)


@admin.register(Inscription)
class InscriptionAvecCertificatAdmin(InscriptionAdmin):
    list_display = (*InscriptionAdmin.list_display, 'document')
    list_select_related = (*InscriptionAdmin.list_select_related, 'certificat')
    actions = (*InscriptionAdmin.actions, 'delivrer_certificat')

    def has_delivrer_permission(self, request):
        return request.user.has_perm('certificates.delivrer_certificat')

    @admin.display(description='certificat')
    def document(self, obj):
        certificat = getattr(obj, 'certificat', None)
        if certificat is None:
            return '—'
        libelle = certificat.numero if certificat.est_valide else f'{certificat.numero} (annulé)'
        return format_html('<a href="{}">{}</a>', reverse('admin:certificates_certificat_change', args=[certificat.pk]), libelle)

    @admin.action(description='Délivrer le certificat / l’attestation', permissions=['delivrer'])
    def delivrer_certificat(self, request, queryset):
        for inscription in queryset.select_related('candidat').order_by('date_creation'):
            try:
                certificat, est_nouveau = services.delivrer(inscription, request.user)
            except services.CertificatImpossible as erreur:
                self.message_user(request, f'{inscription.candidat.nom_complet} : {erreur.message}', messages.ERROR)
                continue
            verbe = 'délivré' if est_nouveau else 'remis en vigueur'
            self.message_user(request, format_html(
                '{} : {} {} (<a href="{}">{}</a>).', inscription.candidat.nom_complet,
                certificat.get_type_display(), verbe,
                reverse('admin:certificates_certificat_change', args=[certificat.pk]), certificat.numero,
            ), messages.SUCCESS)
