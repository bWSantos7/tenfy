from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0006_playerprofile_preferred_modality'),
    ]

    operations = [
        migrations.AddField(
            model_name='playerprofile',
            name='ti_results_cache',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='playerprofile',
            name='ti_rankings_cache',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='playerprofile',
            name='ti_results_synced_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerprofile',
            name='ti_rankings_synced_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerprofile',
            name='ti_sync_error',
            field=models.CharField(blank=True, max_length=300),
        ),
    ]
