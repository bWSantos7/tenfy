from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0005_add_travel_states'),
    ]

    operations = [
        migrations.AddField(
            model_name='playerprofile',
            name='preferred_modality',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Preferred tournament modality: tennis, beach_tennis, padel, wheelchair. Empty = not set.',
                max_length=50,
            ),
        ),
    ]
