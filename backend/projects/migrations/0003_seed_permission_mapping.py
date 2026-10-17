from django.contrib.auth.management import create_permissions
from django.db import migrations

MEMBER_CODENAMES = ['view_project', 'add_task', 'change_task', 'delete_task', 'view_task', 'export_task']
VIEWER_CODENAMES = ['view_project', 'view_task']


def seed(apps, schema_editor):
    # auth_permission rows are normally created by post_migrate, which hasn't
    # run yet on a fresh database, so create them up front.
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    Permission = apps.get_model('auth', 'Permission')
    RolePermission = apps.get_model('projects', 'RolePermission')

    mapping = {
        'admin': Permission.objects.all(),
        'member': Permission.objects.filter(codename__in=MEMBER_CODENAMES),
        'viewer': Permission.objects.filter(codename__in=VIEWER_CODENAMES),
    }
    RolePermission.objects.bulk_create(
        [RolePermission(role=role, permission=p) for role, perms in mapping.items() for p in perms],
        ignore_conflicts=True,
    )


def unseed(apps, schema_editor):
    apps.get_model('projects', 'RolePermission').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0002_rolepermission'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
