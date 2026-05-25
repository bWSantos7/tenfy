from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tournaments', '0007_tournamentedition_has_online_entry_withdrawal_deadline_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='tournamentedition',
            name='entries_source_url',
            field=models.URLField(
                blank=True,
                max_length=500,
                help_text='Melhor URL conhecida para a página de inscritos/chaves desta edição.',
            ),
        ),
        migrations.AddField(
            model_name='tournamentedition',
            name='candidate_entry_links',
            field=models.JSONField(
                default=list,
                blank=True,
                help_text='Lista de URLs candidatas para inscritos/chaves (derivadas ou extraídas).',
            ),
        ),
        migrations.AddField(
            model_name='tournamentedition',
            name='needs_sync',
            field=models.BooleanField(
                default=True,
                db_index=True,
                help_text='True quando os dados de inscritos precisam ser sincronizados.',
            ),
        ),
        migrations.AddField(
            model_name='tournamentedition',
            name='last_synced_at',
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text='Última vez que os inscritos foram sincronizados com a fonte externa.',
            ),
        ),
        migrations.AddField(
            model_name='tournamentedition',
            name='sync_priority',
            field=models.PositiveSmallIntegerField(
                default=5,
                help_text='Prioridade de sincronização (0=menor, 30=urgente). Computado pelo backend.',
            ),
        ),
        migrations.AddField(
            model_name='tournamentedition',
            name='parser_available',
            field=models.BooleanField(
                default=False,
                help_text='True quando existe conector/parser capaz de extrair inscritos desta fonte.',
            ),
        ),
        migrations.AddField(
            model_name='tournamentedition',
            name='parser_limitation',
            field=models.CharField(
                max_length=300,
                blank=True,
                help_text='Descrição da limitação do parser para esta fonte, quando aplicável.',
            ),
        ),
        migrations.AddField(
            model_name='tournamentedition',
            name='validation_errors',
            field=models.JSONField(
                default=list,
                blank=True,
                help_text='Erros de validação detectados na ingestão (email em cidade, UF inválida, etc.).',
            ),
        ),
    ]
