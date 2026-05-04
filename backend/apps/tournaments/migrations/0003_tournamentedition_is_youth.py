from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tournaments', '0002_tournamentcategory_max_participants'),
    ]

    operations = [
        migrations.AddField(
            model_name='tournamentedition',
            name='is_youth',
            field=models.BooleanField(
                blank=True,
                db_index=True,
                help_text='True = torneio infantojuvenil (categorias até 18 anos). Null = não classificado.',
                null=True,
            ),
        ),
    ]
