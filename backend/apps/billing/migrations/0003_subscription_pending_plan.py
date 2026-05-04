from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0002_rename_billing_pay_user_idx_billing_pay_user_id_c9be81_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscription',
            name='pending_billing_period',
            field=models.CharField(blank=True, choices=[('monthly', 'Mensal'), ('yearly', 'Anual')], max_length=10),
        ),
        migrations.AddField(
            model_name='subscription',
            name='pending_plan',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pending_subscriptions', to='billing.plan'),
        ),
    ]
