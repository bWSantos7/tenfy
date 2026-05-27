"""
Enable the pg_trgm PostgreSQL extension and add a GIN trigram index on
FederationEntry.player_name to accelerate fuzzy name matching at scale.
"""
from django.contrib.postgres.operations import BtreeGinExtension, TrigramExtension
from django.contrib.postgres.indexes import GinIndex
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('registrations', '0008_matchinglog'),
    ]

    operations = [
        # Activate extensions (idempotent — safe to run multiple times)
        TrigramExtension(),
        BtreeGinExtension(),

        # GIN trigram index on player_name for fast similarity queries
        migrations.AddIndex(
            model_name='federationentry',
            index=GinIndex(
                fields=['player_name'],
                name='fedentry_player_name_gin_idx',
                opclasses=['gin_trgm_ops'],
            ),
        ),
    ]
