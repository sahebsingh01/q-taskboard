from django.contrib.auth.management import create_permissions
from django.db import migrations

MAPPING = {
    'admin': ['add_comment', 'view_comment', 'view_activity'],
    'member': ['add_comment', 'view_comment', 'view_activity'],
    'viewer': ['view_comment', 'view_activity'],
}


def seed(apps, schema_editor):
    # Permissions for the new models don't exist until post_migrate runs.
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    Permission = apps.get_model('auth', 'Permission')
    RolePermission = apps.get_model('projects', 'RolePermission')
    RolePermission.objects.bulk_create(
        [
            RolePermission(role=role, permission=p)
            for role, codenames in MAPPING.items()
            for p in Permission.objects.filter(content_type__app_label='projects', codename__in=codenames)
        ],
        ignore_conflicts=True,
    )


def unseed(apps, schema_editor):
    codenames = {c for codenames in MAPPING.values() for c in codenames}
    apps.get_model('projects', 'RolePermission').objects.filter(permission__codename__in=codenames).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0006_comments_activity'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
