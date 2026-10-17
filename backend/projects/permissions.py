from .models import RolePermission


def get_role_permissions(role):
    return set(
        RolePermission.objects
        .filter(role=role)
        .values_list('permission__codename', flat=True)
    )


def has_permission(membership, codename):
    if membership is None:
        return False
    return RolePermission.objects.filter(role=membership.role, permission__codename=codename).exists()


def get_user_project_permissions(user):
    """Map each project the user belongs to onto their role and permission codenames."""
    memberships = list(user.memberships.values_list('project_id', 'role'))
    codenames_by_role = {}
    for role, codename in (
        RolePermission.objects
        .filter(role__in={role for _, role in memberships})
        .values_list('role', 'permission__codename')
    ):
        codenames_by_role.setdefault(role, set()).add(codename)
    return {
        str(project_id): {'role': role, 'permissions': sorted(codenames_by_role.get(role, ()))}
        for project_id, role in memberships
    }
