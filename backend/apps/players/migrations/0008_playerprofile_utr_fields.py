from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0007_playerprofile_ti_cache'),
    ]

    operations = [
        migrations.AddField(
            model_name='playerprofile',
            name='utr_player_id',
            field=models.CharField(blank=True, help_text='Confirmed UTR profile ID', max_length=50),
        ),
        migrations.AddField(
            model_name='playerprofile',
            name='utr_display_name',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='playerprofile',
            name='utr_singles',
            field=models.CharField(blank=True, help_text='e.g. 4.35 or 4.xx', max_length=20),
        ),
        migrations.AddField(
            model_name='playerprofile',
            name='utr_doubles',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='playerprofile',
            name='utr_profile_url',
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name='playerprofile',
            name='utr_synced_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='playerprofile',
            name='utr_sync_error',
            field=models.CharField(blank=True, max_length=300),
        ),
    ]
