from django.contrib.postgres.operations import UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('tournaments', '0008_tournamentedition_sync_fields'),
    ]

    operations = [
        UnaccentExtension(),
    ]
