from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('watchlist', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='TournamentResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('category_played', models.CharField(blank=True, max_length=200)),
                ('position', models.PositiveIntegerField(blank=True, help_text='Final position (1 = winner)', null=True)),
                ('wins', models.PositiveIntegerField(default=0)),
                ('losses', models.PositiveIntegerField(default=0)),
                ('notes', models.TextField(blank=True)),
                ('watchlist_item', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='result',
                    to='watchlist.watchlistitem',
                )),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
