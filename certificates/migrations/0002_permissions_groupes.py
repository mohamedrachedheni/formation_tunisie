from django.contrib.auth.management import create_permissions
from django.db import migrations

# Droits sur les certificats par rôle :
# - Administrateur : consultation, délivrance (et mise à jour), annulation ;
# - Gestionnaire : consultation et délivrance, sans annulation.
# Aucun rôle n'a les droits standards d'ajout, de modification ou de suppression :
# un certificat n'est créé, corrigé ou annulé que par les règles métier (certificates/services.py).
CODENAMES_PAR_GROUPE = {
    'Administrateur': ('view_certificat', 'delivrer_certificat', 'annuler_certificat'),
    'Gestionnaire': ('view_certificat', 'delivrer_certificat'),
}


def attribuer_permissions(apps, schema_editor):
    # Les permissions ne sont normalement créées qu'après toutes les migrations (signal post_migrate) :
    # on les crée ici explicitement pour pouvoir les attribuer dès maintenant.
    app_config = apps.get_app_config('certificates')
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    for nom_groupe, codenames in CODENAMES_PAR_GROUPE.items():
        groupe, _ = Group.objects.get_or_create(name=nom_groupe)
        groupe.permissions.add(*Permission.objects.filter(content_type__app_label='certificates', codename__in=codenames))


def retirer_permissions(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    permissions = Permission.objects.filter(content_type__app_label='certificates')
    for groupe in Group.objects.filter(name__in=CODENAMES_PAR_GROUPE):
        groupe.permissions.remove(*permissions)


class Migration(migrations.Migration):

    dependencies = [
        ('certificates', '0001_initial'),
        ('accounts', '0002_creer_groupes_roles'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(attribuer_permissions, retirer_permissions),
    ]
