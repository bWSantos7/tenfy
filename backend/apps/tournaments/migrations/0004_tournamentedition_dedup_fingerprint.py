from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tournaments', '0003_tournamentedition_is_youth'),
    ]

    operations = [
        migrations.AddField(
            model_name='tournamentedition',
            name='dedup_fingerprint',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='Short hash for cross-source dedup (title+date+city). Empty = not computed.',
                max_length=16,
            ),
        ),
    ]
