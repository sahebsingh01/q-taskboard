import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0003_seed_permission_mapping'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ExportJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(
                    choices=[
                        ('running', 'Running'),
                        ('succeeded', 'Succeeded'),
                        ('partial', 'Partially succeeded'),
                        ('failed', 'Failed'),
                    ],
                    default='running',
                    max_length=10,
                )),
                ('total', models.IntegerField(default=0)),
                ('created', models.IntegerField(default=0)),
                ('updated', models.IntegerField(default=0)),
                ('failed', models.IntegerField(default=0)),
                ('errors', models.JSONField(default=list)),
                ('error', models.TextField(blank=True, default='')),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('project', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='export_jobs',
                    to='projects.project',
                )),
                ('triggered_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'export_jobs',
                'indexes': [models.Index(fields=['project', 'status'], name='export_jobs_project_status_idx')],
            },
        ),
    ]
