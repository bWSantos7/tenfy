from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0003_subscription_pending_plan'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='plan',
            name='max_members',
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text='Total de membros permitidos (titular + dependentes). Individual=1, Família=5+.',
            ),
        ),
        migrations.CreateModel(
            name='FamilyMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(
                    choices=[('pending', 'Pendente'), ('active', 'Ativo'), ('removed', 'Removido')],
                    default='pending',
                    max_length=10,
                )),
                ('accepted_at', models.DateTimeField(blank=True, null=True)),
                ('subscription', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='family_members',
                    to='billing.subscription',
                )),
                ('member_user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='family_memberships',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
                'unique_together': {('subscription', 'member_user')},
            },
        ),
    ]
