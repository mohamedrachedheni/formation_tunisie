from django.contrib import admin
from django.db.models import Count

from .models import Categorie, DocumentFormation, Formation, ModuleProgramme


@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ('nom', 'ordre', 'est_active', 'nombre_formations')
    list_editable = ('ordre', 'est_active')
    list_filter = ('est_active',)
    search_fields = ('nom',)
    prepopulated_fields = {'slug': ('nom',)}
    readonly_fields = ('uuid', 'date_creation', 'date_modification')

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(nb_formations=Count('formations'))

    @admin.display(description='formations', ordering='nb_formations')
    def nombre_formations(self, obj):
        return obj.nb_formations


class ModuleProgrammeInline(admin.TabularInline):
    model = ModuleProgramme
    extra = 1
    fields = ('ordre', 'titre', 'duree_heures', 'contenu')


class DocumentFormationInline(admin.TabularInline):
    model = DocumentFormation
    extra = 1
    fields = ('titre', 'fichier', 'est_public')


@admin.register(Formation)
class FormationAdmin(admin.ModelAdmin):
    list_display = ('titre', 'categorie', 'prix', 'duree_heures', 'modalite', 'est_publiee', 'est_a_la_une', 'est_certifiante')
    list_editable = ('est_a_la_une',)
    list_filter = ('est_publiee', 'est_a_la_une', 'categorie', 'modalite', 'niveau', 'est_certifiante')
    list_select_related = ('categorie',)
    search_fields = ('titre', 'resume')
    prepopulated_fields = {'slug': ('titre',)}
    readonly_fields = ('uuid', 'date_creation', 'date_modification')
    inlines = (ModuleProgrammeInline, DocumentFormationInline)
    actions = ('publier', 'depublier')
    fieldsets = (
        (None, {'fields': ('categorie', 'titre', 'slug', 'resume', 'image')}),
        ('Contenu', {'fields': ('description', 'objectifs', 'public_vise', 'prerequis')}),
        ('Caractéristiques', {'fields': ('duree_heures', 'prix', 'niveau', 'modalite', 'est_certifiante')}),
        ('Publication', {'fields': ('est_publiee', 'est_a_la_une')}),
        ('Suivi', {'classes': ('collapse',), 'fields': ('uuid', 'date_creation', 'date_modification')}),
    )

    @admin.action(description='Publier les formations sélectionnées', permissions=['change'])
    def publier(self, request, queryset):
        nombre = queryset.update(est_publiee=True)
        self.message_user(request, f'{nombre} formation(s) publiée(s).')

    @admin.action(description='Retirer du site les formations sélectionnées', permissions=['change'])
    def depublier(self, request, queryset):
        nombre = queryset.update(est_publiee=False)
        self.message_user(request, f'{nombre} formation(s) retirée(s) du site.')
