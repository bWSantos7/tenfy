"""
Sync migration: update FederationEntry.source help_text to include 'cosat'.

Context:
  FederationEntry.SOURCE_COSAT = 'cosat' was added to models.py in commit 5eddf6a,
  and the source field help_text was updated to include cosat as a valid value.
  No migration was generated at that time. This migration records that change
  in the migration history.

Safe: AlterField on help_text only — produces no SQL, no schema change.
      help_text is a metadata-only attribute not stored in the database.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registrations', '0005_remove_fedentry_removed_idx'),
    ]

    operations = [
        migrations.AlterField(
            model_name='federationentry',
            name='source',
            field=models.CharField(
                default='manual',
                help_text='Origem: cbt, fpt, fct, cosat, manual…',
                max_length=50,
            ),
        ),
    ]
