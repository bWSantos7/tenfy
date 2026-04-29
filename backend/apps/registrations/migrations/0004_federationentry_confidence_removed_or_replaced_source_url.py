"""
Add confidence, removed_or_replaced, replacement_reason, source_url to FederationEntry.
All operations are additive (no DROP/ALTER COLUMN) — safe for production.
Generated 2026-04-28.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registrations', '0003_rename_reg_fedentry_ed_cat_idx_registratio_edition_11bcf8_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='federationentry',
            name='removed_or_replaced',
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text='True se o atleta foi removido/substituído por critério de ranking da federação',
            ),
        ),
        migrations.AddField(
            model_name='federationentry',
            name='replacement_reason',
            field=models.CharField(
                max_length=300,
                blank=True,
                default='',
                help_text='Motivo da remoção/substituição conforme publicado pela federação',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='federationentry',
            name='source_url',
            field=models.URLField(
                max_length=500,
                blank=True,
                default='',
                help_text='URL pública onde esta entrada foi encontrada',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='federationentry',
            name='confidence',
            field=models.CharField(
                max_length=10,
                choices=[
                    ('high', 'Alta — API oficial ou confirmação manual'),
                    ('medium', 'Média — scraping de página pública'),
                    ('low', 'Baixa — inferido ou incompleto'),
                ],
                default='medium',
                help_text='Grau de confiança nos dados desta entrada',
            ),
        ),
        migrations.AddIndex(
            model_name='federationentry',
            index=models.Index(fields=['removed_or_replaced'], name='reg_fedentry_removed_idx'),
        ),
    ]
