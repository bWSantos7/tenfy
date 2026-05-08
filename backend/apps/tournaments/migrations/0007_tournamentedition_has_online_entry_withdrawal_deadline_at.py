from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tournaments', '0006_tournamentedition_is_published'),
    ]

    operations = [
        migrations.AddField(
            model_name='tournamentedition',
            name='withdrawal_deadline_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text='Deadline to withdraw from tournament after registering.',
            ),
        ),
        migrations.AddField(
            model_name='tournamentedition',
            name='has_online_entry',
            field=models.BooleanField(
                default=False,
                help_text='True when the source indicates online registration is available.',
            ),
        ),
    ]
