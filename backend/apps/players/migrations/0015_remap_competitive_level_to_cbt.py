"""Task 12: remapeia competitive_level (habilidade) para os níveis CBT por idade.

Faixas definidas com o usuário:
  ≤10  → kids     (Crianças)
  11-18 → youth   (Juvenil)
  19-59 → pro     (Profissional)
  ≥60  → seniors  (Idosos)
Sem idade (birth_year/birth_date ausentes) → pro (Profissional).
"""
from datetime import date

from django.db import migrations


def _age(birth_year, birth_date, today):
    if birth_date:
        return today.year - birth_date.year - (
            (today.month, today.day) < (birth_date.month, birth_date.day)
        )
    if birth_year:
        return today.year - birth_year
    return None


def _level_for_age(age):
    if age is None:
        return 'pro'
    if age <= 10:
        return 'kids'
    if age <= 18:
        return 'youth'
    if age <= 59:
        return 'pro'
    return 'seniors'


def remap_forward(apps, schema_editor):
    PlayerProfile = apps.get_model('players', 'PlayerProfile')
    today = date.today()
    for profile in PlayerProfile.objects.all().only('id', 'birth_year', 'birth_date', 'competitive_level'):
        new_level = _level_for_age(_age(profile.birth_year, profile.birth_date, today))
        if profile.competitive_level != new_level:
            profile.competitive_level = new_level
            profile.save(update_fields=['competitive_level'])


def remap_backward(apps, schema_editor):
    # Sem rollback semântico (níveis antigos de habilidade não são recuperáveis);
    # mantém os valores atuais.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0014_alter_playerprofile_competitive_level'),
    ]

    operations = [
        migrations.RunPython(remap_forward, remap_backward),
    ]
