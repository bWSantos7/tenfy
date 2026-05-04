import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eligibility', '0001_initial'),
        ('tournaments', '0004_tournamentedition_dedup_fingerprint'),
    ]

    operations = [
        migrations.CreateModel(
            name='TournamentRuleBinding',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('binding_reason', models.CharField(blank=True, help_text='e.g. "2026 season rules"', max_length=200)),
                ('is_primary', models.BooleanField(default=True, help_text='Primary binding used for eligibility evaluation')),
                ('edition', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='rule_bindings',
                    to='tournaments.tournamentedition',
                )),
                ('ruleset', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='tournament_bindings',
                    to='eligibility.ruleset',
                )),
                ('pinned_version', models.ForeignKey(
                    blank=True,
                    help_text='Leave blank to always use the active version of the ruleset',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='pinned_bindings',
                    to='eligibility.ruleversion',
                )),
            ],
            options={
                'ordering': ['-is_primary', '-created_at'],
                'unique_together': {('edition', 'ruleset')},
            },
        ),
        migrations.AddIndex(
            model_name='tournamentrulebinding',
            index=models.Index(fields=['edition', 'is_primary'], name='elig_trb_edition_primary_idx'),
        ),
    ]
