import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Feature',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('code', models.CharField(max_length=60, unique=True)),
                ('description', models.TextField(blank=True)),
            ],
            options={'ordering': ['code']},
        ),
        migrations.CreateModel(
            name='Plan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=60)),
                ('slug', models.SlugField(max_length=30, unique=True)),
                ('price_monthly', models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ('price_yearly', models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ('description', models.TextField(blank=True)),
                ('highlight_label', models.CharField(blank=True, help_text='e.g. "Mais popular"', max_length=40)),
                ('display_order', models.PositiveSmallIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={'ordering': ['display_order']},
        ),
        migrations.CreateModel(
            name='PlanFeature',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('limit', models.PositiveIntegerField(blank=True, help_text='NULL = unlimited', null=True)),
                ('notes', models.CharField(blank=True, max_length=200)),
                ('feature', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='plan_features', to='billing.feature')),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='plan_features', to='billing.plan')),
            ],
            options={'unique_together': {('plan', 'feature')}},
        ),
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('billing_period', models.CharField(choices=[('monthly', 'Mensal'), ('yearly', 'Anual')], default='monthly', max_length=10)),
                ('status', models.CharField(choices=[('active', 'Ativa'), ('pending', 'Pendente'), ('canceled', 'Cancelada'), ('expired', 'Expirada'), ('unpaid', 'Inadimplente'), ('trial', 'Trial')], default='pending', max_length=15)),
                ('start_date', models.DateField(blank=True, null=True)),
                ('next_due_date', models.DateField(blank=True, null=True)),
                ('cancel_at_period_end', models.BooleanField(default=False)),
                ('canceled_at', models.DateTimeField(blank=True, null=True)),
                ('asaas_customer_id', models.CharField(blank=True, max_length=60)),
                ('asaas_subscription_id', models.CharField(blank=True, max_length=60)),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='subscriptions', to='billing.plan')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='subscription', to=settings.AUTH_USER_MODEL)),
            ],
            options={'indexes': [models.Index(fields=['status'], name='billing_sub_status_idx'), models.Index(fields=['next_due_date'], name='billing_sub_next_due_idx')]},
        ),
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('payment_method', models.CharField(blank=True, choices=[('credit_card', 'Cartão de crédito'), ('pix', 'Pix'), ('debit_card', 'Cartão de débito'), ('boleto', 'Boleto')], max_length=15)),
                ('status', models.CharField(choices=[('pending', 'Pendente'), ('paid', 'Pago'), ('failed', 'Falhou'), ('refunded', 'Estornado'), ('overdue', 'Vencido')], default='pending', max_length=15)),
                ('transaction_id', models.CharField(blank=True, max_length=120)),
                ('asaas_payment_id', models.CharField(blank=True, max_length=60)),
                ('due_date', models.DateField(blank=True, null=True)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('description', models.CharField(blank=True, max_length=200)),
                ('pix_code', models.TextField(blank=True, help_text='Pix copia-e-cola')),
                ('pix_qr_code', models.TextField(blank=True, help_text='Base64 QR code image')),
                ('boleto_url', models.URLField(blank=True)),
                ('raw_response', models.JSONField(blank=True, default=dict)),
                ('subscription', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payments', to='billing.subscription')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payments', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['user', '-created_at'], name='billing_pay_user_idx'),
                    models.Index(fields=['status'], name='billing_pay_status_idx'),
                    models.Index(fields=['asaas_payment_id'], name='billing_pay_asaas_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='WebhookEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('event_type', models.CharField(max_length=80)),
                ('asaas_id', models.CharField(blank=True, db_index=True, max_length=60)),
                ('payload', models.JSONField(default=dict)),
                ('processed', models.BooleanField(default=False)),
                ('error', models.CharField(blank=True, max_length=300)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
