from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_remove_user_phone_verified'),
    ]

    operations = [
        migrations.CreateModel(
            name='CoachAthlete',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('notes', models.CharField(blank=True, max_length=300)),
                ('coach', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='athletes',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('athlete', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='coaches',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-created_at'], 'unique_together': {('coach', 'athlete')}},
        ),
    ]
