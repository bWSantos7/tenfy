from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tournaments', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='tournamentcategory',
            name='max_participants',
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text='Limite de vagas nesta categoria. Null = sem limite definido.',
            ),
        ),
    ]
