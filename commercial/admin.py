from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html_join

from .models import DemandeContact


@admin.register(DemandeContact)
class DemandeContactAdmin(admin.ModelAdmin):
    list_display = ('date_creation', 'nom', 'coordonnees', 'formation', 'source', 'statut', 'traitee_par')
    list_display_links = ('date_creation', 'nom')
    list_filter = ('statut', 'source', 'formation')
    list_select_related = ('formation', 'traitee_par')
    search_fields = ('nom', 'email', 'telephone', 'message')
    # Pas de date_hierarchy tant que les tables de fuseaux horaires de MariaDB ne sont pas chargées
    # (avec USE_TZ=True, Django a besoin de CONVERT_TZ pour regrouper par date).
    actions = ('marquer_en_cours', 'marquer_traitee')

    CHAMPS_DEMANDEUR = ('nom', 'email', 'telephone', 'formation', 'message', 'source')
    CHAMPS_SUIVI = ('uuid', 'date_creation', 'date_modification')

    fieldsets = (
        ('Demande', {'fields': CHAMPS_DEMANDEUR}),
        ('Traitement', {'fields': ('statut', 'traitee_par', 'notes')}),
        ('Suivi', {'classes': ('collapse',), 'fields': CHAMPS_SUIVI}),
    )

    def get_readonly_fields(self, request, obj=None):
        # Le contenu d'une demande reçue n'est jamais modifié : seuls le statut,
        # le responsable et les notes internes le sont. À la création manuelle
        # (demande reçue par téléphone ou WhatsApp), tous les champs sont saisissables.
        if obj is None:
            return self.CHAMPS_SUIVI + ('traitee_par',)
        return self.CHAMPS_DEMANDEUR + self.CHAMPS_SUIVI + ('traitee_par',)

    def get_changeform_initial_data(self, request):
        # Une demande saisie depuis l'administration vient en général du téléphone.
        initial = super().get_changeform_initial_data(request)
        initial.setdefault('source', DemandeContact.Source.TELEPHONE)
        return initial

    def save_model(self, request, obj, form, change):
        # Dès qu'une demande quitte le statut « Nouvelle », on retient qui l'a prise en charge.
        if obj.statut != DemandeContact.Statut.NOUVELLE and obj.traitee_par is None:
            obj.traitee_par = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description='coordonnées')
    def coordonnees(self, obj):
        return format_html_join(' · ', '{}', ((valeur,) for valeur in (obj.telephone, obj.email) if valeur))

    def _changer_statut(self, request, queryset, statut):
        # traitee_par n'est renseigné que s'il est vide : on ne remplace pas le responsable existant.
        # update() ne renseigne pas date_modification (auto_now) : on le fait explicitement.
        maintenant = timezone.now()
        sans_responsable = queryset.filter(traitee_par__isnull=True).update(
            statut=statut, traitee_par=request.user, date_modification=maintenant,
        )
        avec_responsable = queryset.filter(traitee_par__isnull=False).exclude(statut=statut).update(
            statut=statut, date_modification=maintenant,
        )
        return sans_responsable + avec_responsable

    @admin.action(description='Marquer « En cours »', permissions=['change'])
    def marquer_en_cours(self, request, queryset):
        nombre = self._changer_statut(request, queryset, DemandeContact.Statut.EN_COURS)
        self.message_user(request, f'{nombre} demande(s) marquée(s) « En cours ».')

    @admin.action(description='Marquer « Traitée »', permissions=['change'])
    def marquer_traitee(self, request, queryset):
        nombre = self._changer_statut(request, queryset, DemandeContact.Statut.TRAITEE)
        self.message_user(request, f'{nombre} demande(s) marquée(s) « Traitée ».')
