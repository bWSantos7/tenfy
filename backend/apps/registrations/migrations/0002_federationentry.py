from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('registrations', '0001_initial'),
        ('tournaments', '0003_tournamentedition_is_youth'),
    ]

    operations = [
        migrations.CreateModel(
            name='FederationEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('category_text', models.CharField(
                    help_text='Categoria conforme publicada pela federação (ex: Sub-12 Masculino)',
                    max_length=200,
                )),
                ('player_name', models.CharField(max_length=200)),
                ('player_external_id', models.CharField(
                    blank=True,
                    help_text='ID do jogador na federação de origem',
                    max_length=100,
                )),
                ('ranking_position', models.PositiveIntegerField(
                    blank=True,
                    help_text='Posição no ranking (menor = melhor)',
                    null=True,
                )),
                ('payment_status', models.CharField(
                    choices=[('paid', 'Pago'), ('pending', 'Pendente'), ('unknown', 'Não informado')],
                    db_index=True,
                    default='unknown',
                    max_length=20,
                )),
                ('source', models.CharField(
                    default='manual',
                    help_text='Origem: cbt, fpt, fct, manual…',
                    max_length=50,
                )),
                ('notes', models.CharField(blank=True, max_length=300)),
                ('raw_data', models.JSONField(blank=True, default=dict)),
                ('synced_at', models.DateTimeField(auto_now=True)),
                ('edition', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='federation_entries',
                    to='tournaments.tournamentedition',
                )),
            ],
            options={
                'ordering': ['category_text', 'ranking_position', 'player_name'],
            },
        ),
        migrations.AddIndex(
            model_name='federationentry',
            index=models.Index(fields=['edition', 'category_text'], name='reg_fedentry_ed_cat_idx'),
        ),
        migrations.AddIndex(
            model_name='federationentry',
            index=models.Index(fields=['payment_status'], name='reg_fedentry_pay_idx'),
        ),
        migrations.AddIndex(
            model_name='federationentry',
            index=models.Index(fields=['edition', 'source'], name='reg_fedentry_ed_src_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='federationentry',
            unique_together={('edition', 'category_text', 'player_external_id', 'source')},
        ),
    ]
