from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Replaces unique_together('tournament', 'season_year', 'external_id') with a
    conditional UniqueConstraint that only enforces uniqueness when external_id
    is non-empty. This allows multiple editions of the same tournament/year that
    lack a source-provided external ID (external_id='').
    """

    dependencies = [
        ('tournaments', '0010_venue_country_edition_acceptance_list'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='tournamentedition',
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name='tournamentedition',
            constraint=models.UniqueConstraint(
                condition=~models.Q(external_id=''),
                fields=['tournament', 'season_year', 'external_id'],
                name='unique_edition_external_id',
            ),
        ),
    ]
