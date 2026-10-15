from django.contrib import admin, messages
from django.utils import timezone

from . import services
from .forms import InscriptionAjoutForm
from .models import Candidat, Inscription, Session


class InscriptionLectureInline(admin.TabularInline):
    """Liste des inscriptions en lecture seule : les changements passent par l'administration des inscriptions."""

    model = Inscription
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class InscriptionsDeLaSessionInline(InscriptionLectureInline):
    fields = ('candidat', 'statut', 'resultat', 'prix_convenu', 'source', 'date_creation')
    readonly_fields = fields


class InscriptionsDuCandidatInline(InscriptionLectureInline):
    fields = ('session', 'statut', 'resultat', 'prix_convenu', 'source', 'date_creation')
    readonly_fields = fields


# --- Sessions -------------------------------------------------------------------------------

@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('code', 'formation', 'formateur', 'date_debut', 'date_fin', 'places', 'prix_affiche', 'statut', 'est_publiee')
    list_filter = ('statut', 'est_publiee', 'formation', 'formateur')
    list_select_related = ('formation', 'formateur')
    search_fields = ('code', 'formation__titre', 'lieu')
    date_hierarchy = 'date_debut'
    autocomplete_fields = ('formation', 'formateur')
    readonly_fields = ('uuid', 'date_creation', 'date_modification')
    inlines = (InscriptionsDeLaSessionInline,)
    actions = ('publier', 'retirer_du_site')
    fieldsets = (
        (None, {'fields': ('formation', 'formateur', 'code')}),
        ('Calendrier et lieu', {'fields': ('date_debut', 'date_fin', 'horaires', 'lieu', 'modalite')}),
        ('Places et tarif', {'fields': ('places_max', 'prix')}),
        ('Statut', {'fields': ('statut', 'est_publiee')}),
        ('Suivi', {'classes': ('collapse',), 'fields': ('uuid', 'date_creation', 'date_modification')}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).avec_places_occupees()

    @admin.display(description='places occupées', ordering='nb_places_occupees')
    def places(self, obj):
        return f'{obj.places_occupees} / {obj.places_max}'

    @admin.display(description='prix (TND)')
    def prix_affiche(self, obj):
        return obj.prix_effectif

    @admin.action(description='Publier sur le site', permissions=['change'])
    def publier(self, request, queryset):
        nombre = queryset.update(est_publiee=True, date_modification=timezone.now())
        self.message_user(request, f'{nombre} session(s) publiée(s).')

    @admin.action(description='Retirer du site', permissions=['change'])
    def retirer_du_site(self, request, queryset):
        nombre = queryset.update(est_publiee=False, date_modification=timezone.now())
        self.message_user(request, f'{nombre} session(s) retirée(s) du site.')


# --- Candidats ------------------------------------------------------------------------------

@admin.register(Candidat)
class CandidatAdmin(admin.ModelAdmin):
    list_display = ('nom_complet', 'telephone', 'email', 'cin', 'gouvernorat', 'date_creation')
    list_display_links = ('nom_complet',)
    list_filter = ('gouvernorat', 'niveau_etudes')
    search_fields = ('nom', 'prenom', 'telephone', 'email', 'cin')
    readonly_fields = ('uuid', 'date_creation', 'date_modification')
    inlines = (InscriptionsDuCandidatInline,)
    fieldsets = (
        ('Identité', {'fields': ('prenom', 'nom', 'cin', 'date_naissance')}),
        ('Coordonnées', {'fields': ('telephone', 'email', 'gouvernorat')}),
        ('Profil', {'fields': ('niveau_etudes', 'profession')}),
        ('Compte', {'fields': ('utilisateur',)}),
        ('Suivi', {'classes': ('collapse',), 'fields': ('uuid', 'date_creation', 'date_modification')}),
    )

    def get_readonly_fields(self, request, obj=None):
        # Rattacher un compte suppose de pouvoir consulter les comptes (réservé à l'administration).
        champs = super().get_readonly_fields(request, obj)
        if not request.user.has_perm('accounts.view_utilisateur'):
            champs = (*champs, 'utilisateur')
        return champs

    @admin.display(description='candidat', ordering='nom')
    def nom_complet(self, obj):
        return obj.nom_complet


# --- Inscriptions ---------------------------------------------------------------------------

@admin.register(Inscription)
class InscriptionAdmin(admin.ModelAdmin):
    list_display = ('candidat', 'session', 'statut', 'resultat', 'prix_convenu', 'source', 'date_creation')
    list_filter = ('statut', 'resultat', 'source', 'session__formation')
    list_select_related = ('candidat', 'session__formation')
    search_fields = ('candidat__nom', 'candidat__prenom', 'candidat__telephone', 'candidat__cin', 'session__code')
    autocomplete_fields = ('candidat', 'session')
    actions = ('confirmer', 'annuler', 'terminer_reussi', 'terminer_echoue', 'remettre_en_attente')

    CHAMPS_SUIVI = ('uuid', 'date_creation', 'date_modification')
    # Après création, seules les notes sont modifiables : les statuts changent par les actions
    # (qui appliquent les règles : places, session ouverte…), le prix et la source sont figés.
    CHAMPS_FIGES = ('candidat', 'session', 'statut', 'resultat', 'prix_convenu', 'source', 'date_confirmation')

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs['form'] = InscriptionAjoutForm
        return super().get_form(request, obj, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return InscriptionAjoutForm._meta.fields
        return (*self.CHAMPS_FIGES, 'notes', *self.CHAMPS_SUIVI)

    def get_readonly_fields(self, request, obj=None):
        return () if obj is None else (*self.CHAMPS_FIGES, *self.CHAMPS_SUIVI)

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial.setdefault('source', Inscription.Source.TELEPHONE)
        return initial

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return
        # Création par le service : contrôles, prix figé, réactivation éventuelle d'une inscription annulée.
        inscription = services.inscrire(
            obj.candidat, obj.session, source=obj.source, prix=form.cleaned_data.get('prix_convenu'), notes=obj.notes,
        )
        obj.pk = inscription.pk
        obj.refresh_from_db()

    # Actions sur les statuts : permission dédiée « valider_inscription ».
    def has_valider_permission(self, request):
        return request.user.has_perm('enrollments.valider_inscription')

    def _appliquer(self, request, queryset, operation, libelle, *args):
        reussites, echecs = 0, []
        for inscription in queryset.select_related('candidat'):
            try:
                operation(inscription, *args)
                reussites += 1
            except services.InscriptionImpossible as erreur:
                echecs.append(f'{inscription.candidat.nom_complet} : {erreur.message}')
        if reussites:
            self.message_user(request, f'{reussites} inscription(s) {libelle}.', messages.SUCCESS)
        for echec in echecs:
            self.message_user(request, echec, messages.ERROR)

    @admin.action(description='Confirmer', permissions=['valider'])
    def confirmer(self, request, queryset):
        self._appliquer(request, queryset.order_by('date_creation'), services.confirmer, 'confirmée(s)')

    @admin.action(description='Annuler', permissions=['valider'])
    def annuler(self, request, queryset):
        self._appliquer(request, queryset, services.annuler, 'annulée(s)')

    @admin.action(description='Clôturer — réussi', permissions=['valider'])
    def terminer_reussi(self, request, queryset):
        self._appliquer(request, queryset, services.terminer, 'clôturée(s) (réussi)', Inscription.Resultat.REUSSI)

    @admin.action(description='Clôturer — échoué', permissions=['valider'])
    def terminer_echoue(self, request, queryset):
        self._appliquer(request, queryset, services.terminer, 'clôturée(s) (échoué)', Inscription.Resultat.ECHOUE)

    @admin.action(description='Remettre en attente (réinscription)', permissions=['valider'])
    def remettre_en_attente(self, request, queryset):
        def reinscrire(inscription):
            if inscription.statut != Inscription.Statut.ANNULEE:
                raise services.InscriptionImpossible('Seule une inscription annulée peut être remise en attente.')
            services.inscrire(inscription.candidat, inscription.session, source=inscription.source)
        self._appliquer(request, queryset, reinscrire, 'remise(s) en attente')
