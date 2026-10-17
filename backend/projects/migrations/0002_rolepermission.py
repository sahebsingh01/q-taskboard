import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('projects', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='task',
            options={'permissions': [('export_task', 'Can export tasks')]},
        ),
        migrations.CreateModel(
            name='RolePermission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(
                    choices=[('admin', 'Admin'), ('member', 'Member'), ('viewer', 'Viewer')],
                    max_length=10,
                )),
                ('permission', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='role_mappings',
                    to='auth.permission',
                )),
            ],
            options={
                'db_table': 'permission_mapping',
                'unique_together': {('role', 'permission')},
            },
        ),
    ]
