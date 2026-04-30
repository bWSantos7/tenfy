"""
Remove the named index reg_fedentry_removed_idx from FederationEntry.

Context:
  Migration 0004 added both db_index=True on the removed_or_replaced field
  (which creates an unnamed DB index automatically) AND a separate named
  AddIndex operation for the same field. This creates a redundant duplicate.

  Django's migration autodetector detects the mismatch between the named
  index in migration history and the model's Meta.indexes, and flags a
  pending RemoveIndex change.

  This migration removes the named duplicate. The unnamed index from
  db_index=True remains and provides the same performance benefit.

Safe: RemoveIndex is non-destructive. The field's db_index=True unnamed
index continues to serve query optimization on removed_or_replaced.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('registrations', '0004_federationentry_confidence_removed_or_replaced_source_url'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='federationentry',
            name='reg_fedentry_removed_idx',
        ),
    ]
