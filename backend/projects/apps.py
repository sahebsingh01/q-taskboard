from django.apps import AppConfig
from django.db.models.signals import post_migrate


def grant_admin_all_permissions(apps, using, **kwargs):
    """Keep "admin can do everything" true as new models add permissions."""
    try:
        Permission = apps.get_model('auth', 'Permission')
        RolePermission = apps.get_model('projects', 'RolePermission')
    except LookupError:
        return  # migrated backwards past the mapping table
    mapped = RolePermission.objects.using(using).filter(role='admin').values_list('permission_id', flat=True)
    RolePermission.objects.using(using).bulk_create(
        [RolePermission(role='admin', permission=p) for p in Permission.objects.using(using).exclude(id__in=mapped)],
        ignore_conflicts=True,
    )


class ProjectsConfig(AppConfig):
    name = 'projects'

    def ready(self):
        post_migrate.connect(grant_admin_all_permissions, dispatch_uid='projects.grant_admin_all_permissions')
