from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.query_utils


def _invite_token():
    import uuid
    return f'inv_{uuid.uuid4().hex}'


def _invite_expires():
    from datetime import timedelta
    from django.utils import timezone
    return timezone.now() + timedelta(days=7)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_alter_coachathlete_unique_together_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DependentInvite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pendente'),
                        ('accepted', 'Aceito'),
                        ('declined', 'Recusado'),
                        ('canceled', 'Cancelado'),
                        ('expired', 'Expirado'),
                    ],
                    default='pending',
                    max_length=10,
                )),
                ('token', models.CharField(editable=False, max_length=64, unique=True)),
                ('expires_at', models.DateTimeField()),
                ('responded_at', models.DateTimeField(blank=True, null=True)),
                ('parent', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sent_dependent_invites',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('invitee', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='received_dependent_invites',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='dependentinvite',
            index=models.Index(fields=['invitee', 'status'], name='accounts_de_invitee_idx'),
        ),
        migrations.AddIndex(
            model_name='dependentinvite',
            index=models.Index(fields=['parent', 'status'], name='accounts_de_parent_idx'),
        ),
        migrations.AddConstraint(
            model_name='dependentinvite',
            constraint=models.UniqueConstraint(
                condition=django.db.models.query_utils.Q(status='pending'),
                fields=['parent', 'invitee'],
                name='unique_pending_dependent_invite',
            ),
        ),
    ]
