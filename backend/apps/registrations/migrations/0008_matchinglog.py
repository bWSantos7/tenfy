import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registrations', '0007_federationentry_player_country'),
        ('players', '0006_playerprofile_preferred_modality'),
    ]

    operations = [
        migrations.CreateModel(
            name='MatchingLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('confidence', models.CharField(
                    choices=[
                        ('high', 'Alta'),
                        ('medium', 'Média'),
                        ('low', 'Baixa'),
                        ('none', 'Sem match'),
                    ],
                    default='none',
                    max_length=10,
                )),
                ('method', models.CharField(
                    choices=[
                        ('external_id', 'ID externo (match exato)'),
                        ('name_fuzzy', 'Nome fuzzy (SequenceMatcher)'),
                        ('none', 'Sem correspondência'),
                    ],
                    default='none',
                    max_length=20,
                )),
                ('score', models.FloatField(blank=True, null=True)),
                ('registration_created', models.BooleanField(default=False)),
                ('entry', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='matching_logs',
                    to='registrations.federationentry',
                )),
                ('profile', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='matching_logs',
                    to='players.playerprofile',
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='matchinglog',
            index=models.Index(fields=['entry'], name='matchinglog_entry_idx'),
        ),
        migrations.AddIndex(
            model_name='matchinglog',
            index=models.Index(fields=['profile'], name='matchinglog_profile_idx'),
        ),
    ]
