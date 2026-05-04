from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_alter_coachathlete_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='ParentChild',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('child', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='parent_links',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('parent', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='children_links',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
                'unique_together': {('parent', 'child')},
            },
        ),
    ]
