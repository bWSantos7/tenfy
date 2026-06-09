from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_rename_accounts_de_invitee_idx_accounts_de_invitee_54700d_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='failed_login_attempts',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='user',
            name='login_locked_until',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='last_failed_login_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
