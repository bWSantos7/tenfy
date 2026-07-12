"""Seeds the canonical PlayerCategory taxonomy."""
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.players.models import PlayerCategory


CATEGORIES = []

# FPT classes (1..5) for both genders, with 1/2 suffixes (M1, M2)
for level in range(1, 6):
    for gender in ['M', 'F']:
        for suffix in ['', '1', '2']:
            code = f'{level}{gender}{suffix}'
            CATEGORIES.append({
                'taxonomy': PlayerCategory.TAXONOMY_FPT_CLASS,
                'code': code,
                'label_ptbr': f'{level}ª Classe {("Masculino" if gender=="M" else "Feminino")} {("M"+suffix if suffix else "")}'.strip(),
                'gender_scope': gender,
                'class_level': level,
            })

# Principiante
for gender in ['M', 'F']:
    CATEGORIES.append({
        'taxonomy': PlayerCategory.TAXONOMY_FPT_CLASS,
        'code': f'PR{gender}',
        'label_ptbr': f'Principiante {("Masculino" if gender=="M" else "Feminino")}',
        'gender_scope': gender,
        'class_level': 5,
    })

# CBT / FPT youth ages: 10, 12, 14, 16, 18 — exact age match
for age in [10, 12, 14, 16, 18]:
    for gender in ['M', 'F']:
        CATEGORIES.append({
            'taxonomy': PlayerCategory.TAXONOMY_CBT_AGE,
            'code': f'{age}{gender}',
            'label_ptbr': f'Sub-{age} {("Masculino" if gender=="M" else "Feminino")}',
            'gender_scope': gender,
            'min_age': age,
            'max_age': age,
        })

# Kids: faixas amplas (10U/12U, uso legado/genérico) ...
for tier in ['10U', '12U']:
    for gender in ['M', 'F']:
        max_age = int(tier[:-1])
        CATEGORIES.append({
            'taxonomy': PlayerCategory.TAXONOMY_KIDS,
            'code': f'{tier}{gender}',
            'label_ptbr': f'Kids {tier} {("Masculino" if gender=="M" else "Feminino")}',
            'gender_scope': gender,
            'min_age': 0,
            'max_age': max_age,
        })

# ... e idade exata 5-9/11 (tournament-extractor: KIDS_MIN_AGE=5/MAX_AGE=11),
# no mesmo esquema exato-por-idade do CBT_AGE acima — é o formato real das
# categorias vindas de CBT/Federações/FPT (ex.: "8 Anos Masculino Simples").
# 10 já existe no bloco CBT_AGE acima; não duplica aqui.
for age in [5, 6, 7, 8, 9, 11]:
    for gender in ['M', 'F']:
        CATEGORIES.append({
            'taxonomy': PlayerCategory.TAXONOMY_KIDS,
            'code': f'{age}{gender}',
            'label_ptbr': f'Kids {age} {("Masculino" if gender=="M" else "Feminino")}',
            'gender_scope': gender,
            'min_age': age,
            'max_age': age,
        })

# Seniors: 30+, 35+, 40+, 45+, 50+, 55+, 60+, 65+, 70+, 75+
for age in [30, 35, 40, 45, 50, 55, 60, 65, 70, 75]:
    for gender in ['M', 'F']:
        CATEGORIES.append({
            'taxonomy': PlayerCategory.TAXONOMY_SENIORS,
            'code': f'{age}+{gender}',
            'label_ptbr': f'{age}+ {("Masculino" if gender=="M" else "Feminino")}',
            'gender_scope': gender,
            'min_age': age,
        })
    CATEGORIES.append({
        'taxonomy': PlayerCategory.TAXONOMY_SENIORS,
        'code': f'{age}+',
        'label_ptbr': f'{age}+',
        'gender_scope': '*',
        'min_age': age,
    })

# Open / professional
for gender in ['M', 'F']:
    CATEGORIES.append({
        'taxonomy': PlayerCategory.TAXONOMY_OPEN,
        'code': f'OPEN{gender}',
        'label_ptbr': f'Open {("Masculino" if gender=="M" else "Feminino")}',
        'gender_scope': gender,
    })


class Command(BaseCommand):
    help = 'Seeds the canonical PlayerCategory taxonomy.'

    @transaction.atomic
    def handle(self, *args, **options):
        created, updated = 0, 0
        for entry in CATEGORIES:
            obj, was_created = PlayerCategory.objects.update_or_create(
                taxonomy=entry['taxonomy'],
                code=entry['code'],
                gender_scope=entry.get('gender_scope', '*'),
                defaults={
                    'label_ptbr': entry['label_ptbr'],
                    'min_age': entry.get('min_age'),
                    'max_age': entry.get('max_age'),
                    'class_level': entry.get('class_level'),
                    'description': entry.get('description', ''),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
        self.stdout.write(self.style.SUCCESS(
            f'PlayerCategory: created={created} updated={updated} total={created+updated}'
        ))
