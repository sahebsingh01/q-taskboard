import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Project',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=120)),
                ('description', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='owned_projects',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'db_table': 'projects'},
        ),
        migrations.CreateModel(
            name='Membership',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('role', models.CharField(
                    choices=[('admin', 'Admin'), ('member', 'Member'), ('viewer', 'Viewer')],
                    default='member',
                    max_length=10,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('project', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='memberships',
                    to='projects.project',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='memberships',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'memberships',
                'unique_together': {('user', 'project')},
            },
        ),
        migrations.CreateModel(
            name='Task',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=500)),
                ('description', models.TextField(blank=True, null=True)),
                ('status', models.CharField(
                    choices=[
                        ('todo', 'To Do'),
                        ('in_progress', 'In Progress'),
                        ('review', 'Review'),
                        ('done', 'Done'),
                    ],
                    default='todo',
                    max_length=20,
                )),
                ('position', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('assignee', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='assigned_tasks',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('created_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='created_tasks',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('project', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='tasks',
                    to='projects.project',
                )),
            ],
            options={'db_table': 'tasks'},
        ),
        migrations.AddIndex(
            model_name='task',
            index=models.Index(fields=['project', 'status'], name='tasks_project_status_idx'),
        ),
    ]
