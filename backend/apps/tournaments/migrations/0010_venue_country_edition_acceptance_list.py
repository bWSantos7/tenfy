from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tournaments', '0009_unaccent_extension'),
    ]

    operations = [
        migrations.AddField(
            model_name='venue',
            name='country',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='venue',
            name='country_code',
            field=models.CharField(blank=True, help_text='ISO 3166-1 alpha-3 (e.g. BRA, FRA)', max_length=3),
        ),
        migrations.AddField(
            model_name='tournamentedition',
            name='acceptance_list',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Lista de inscritos por seção: [{"section": "main_draw", "players": [...]}]',
            ),
        ),
    ]
