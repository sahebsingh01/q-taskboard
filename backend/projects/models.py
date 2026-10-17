import uuid
from django.db import models
from django.conf import settings


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, null=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_projects')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'projects'


class Membership(models.Model):
    ROLE_CHOICES = [('admin', 'Admin'), ('member', 'Member'), ('viewer', 'Viewer')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='member')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'memberships'
        unique_together = ('user', 'project')


class Task(models.Model):
    STATUS_CHOICES = [
        ('todo', 'To Do'),
        ('in_progress', 'In Progress'),
        ('review', 'Review'),
        ('done', 'Done'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='todo')
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_tasks',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_tasks',
    )
    position = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tasks'
        indexes = [models.Index(fields=['project', 'status'])]
        permissions = [('export_task', 'Can export tasks')]


class RolePermission(models.Model):
    role = models.CharField(max_length=10, choices=Membership.ROLE_CHOICES)
    permission = models.ForeignKey('auth.Permission', on_delete=models.CASCADE, related_name='role_mappings')

    class Meta:
        db_table = 'permission_mapping'
        unique_together = ('role', 'permission')


class ExportJob(models.Model):
    STATUS_CHOICES = [
        ('running', 'Running'),
        ('succeeded', 'Succeeded'),
        ('partial', 'Partially succeeded'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='export_jobs')
    triggered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='running')
    total = models.IntegerField(default=0)
    created = models.IntegerField(default=0)
    skipped = models.IntegerField(default=0)
    failed = models.IntegerField(default=0)
    errors = models.JSONField(default=list)
    error = models.TextField(blank=True, default='')
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'export_jobs'
        indexes = [models.Index(fields=['project', 'status'], name='export_jobs_project_status_idx')]


class AppendOnlyModel(models.Model):
    """A row that can be inserted but never changed or removed through the ORM."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError(f'{type(self).__name__} records are append-only and cannot be edited')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError(f'{type(self).__name__} records are append-only and cannot be deleted')


class Comment(AppendOnlyModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='comments')
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'comments'
        # Append-only: there is deliberately no change/delete permission to grant.
        default_permissions = ('add', 'view')
        indexes = [models.Index(fields=['task', 'created_at'], name='comments_task_created_idx')]


class Activity(AppendOnlyModel):
    VERB_CHOICES = [
        ('task_created', 'Task created'),
        ('status_changed', 'Status changed'),
        ('assignee_changed', 'Assignee changed'),
        ('comment_added', 'Comment added'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='activities')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    verb = models.CharField(max_length=20, choices=VERB_CHOICES)
    # The record outlives the task, so keep its title as it was at the time.
    task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    task_title = models.CharField(max_length=500, blank=True, default='')
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'activities'
        # Written by the system only; people can just read the feed.
        default_permissions = ('view',)
        indexes = [models.Index(fields=['project', '-created_at'], name='activities_project_created_idx')]
