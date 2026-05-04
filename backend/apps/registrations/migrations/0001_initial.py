import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('players', '0001_initial'),
        ('tournaments', '0002_tournamentcategory_max_participants'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TournamentRegistration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('registered_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('ranking_position', models.PositiveIntegerField(
                    blank=True, null=True,
                    help_text='Posição no ranking no momento da inscrição (menor = melhor)',
                )),
                ('payment_status', models.CharField(
                    choices=[
                        ('pending', 'Aguardando pagamento'),
                        ('paid', 'Pago'),
                        ('waived', 'Isento'),
                        ('refunded', 'Reembolsado'),
                    ],
                    db_index=True,
                    default='pending',
                    max_length=20,
                )),
                ('payment_confirmed_at', models.DateTimeField(blank=True, null=True)),
                ('payment_notes', models.TextField(blank=True)),
                ('is_withdrawn', models.BooleanField(db_index=True, default=False)),
                ('withdrawn_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, help_text='Observações internas (admin)')),
                ('category', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='registrations',
                    to='tournaments.tournamentcategory',
                )),
                ('edition', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='registrations',
                    to='tournaments.tournamentedition',
                )),
                ('payment_confirmed_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='payment_confirmations',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('profile', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='registrations',
                    to='players.playerprofile',
                )),
            ],
            options={
                'ordering': ['ranking_position', 'registered_at'],
            },
        ),
        migrations.AddIndex(
            model_name='tournamentregistration',
            index=models.Index(fields=['edition', 'is_withdrawn'], name='reg_edition_withdrawn_idx'),
        ),
        migrations.AddIndex(
            model_name='tournamentregistration',
            index=models.Index(fields=['profile', 'edition'], name='reg_profile_edition_idx'),
        ),
        migrations.AddIndex(
            model_name='tournamentregistration',
            index=models.Index(fields=['payment_status'], name='reg_payment_status_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='tournamentregistration',
            unique_together={('profile', 'edition', 'category')},
        ),
    ]
