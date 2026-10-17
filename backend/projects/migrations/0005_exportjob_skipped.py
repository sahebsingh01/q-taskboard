from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0004_exportjob'),
    ]

    operations = [
        migrations.RemoveField(model_name='exportjob', name='updated'),
        migrations.AddField(
            model_name='exportjob',
            name='skipped',
            field=models.IntegerField(default=0),
        ),
    ]
