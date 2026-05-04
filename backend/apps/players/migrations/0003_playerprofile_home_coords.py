from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0002_playerprofile_unique_user_display_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='playerprofile',
            name='home_lat',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerprofile',
            name='home_lng',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
