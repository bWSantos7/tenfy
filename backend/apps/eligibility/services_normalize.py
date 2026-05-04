"""
Maps raw category strings from sources (e.g. '4M1', '14F', '35+', 'Open Masc.')
to canonical PlayerCategory rows. Falls back to None -> result unknown.
"""
import re
import logging
from functools import lru_cache
from typing import Optional

from apps.players.models import PlayerCategory

logger = logging.getLogger('apps.eligibility.normalize')


CLASS_RE = re.compile(r'^\s*([1-5])\s*([MF])\s*([12])?\s*$', re.IGNORECASE)
AGE_RE = re.compile(r'^\s*(\d{1,2})\s*([MF])\s*$', re.IGNORECASE)
SENIORS_RE = re.compile(r'^\s*(\d{2})\+\s*([MF])?\s*$')
KIDS_RE = re.compile(r'^(?:kids?|red|orange|green|yellow|ball\d+)\s*([MF])?\s*$', re.IGNORECASE)
OPEN_RE = re.compile(r'^(?:open|principal|adulto|absoluto)\s*([MF])?\s*$', re.IGNORECASE)


def _gender(match_groups, default='*'):
    for g in match_groups:
        if g and g.upper() in ('M', 'F'):
            return g.upper()
    return default


@lru_cache(maxsize=1024)
def normalize_category_text(text: str) -> Optional[PlayerCategory]:
    if not text:
        return None
    raw = text.strip()

    # --- FPT class (1..5, M/F, level 1/2) ---
    m = CLASS_RE.match(raw)
    if m:
        klass, gender, lvl = m.groups()
        gender = gender.upper()
        code = f'{klass}{gender}{lvl or ""}'.upper()
        cat = (
            PlayerCategory.objects.filter(
                taxonomy=PlayerCategory.TAXONOMY_FPT_CLASS,
                code__iexact=code,
                gender_scope__in=[gender, '*'],
            ).first()
            or PlayerCategory.objects.filter(
                taxonomy=PlayerCategory.TAXONOMY_FPT_CLASS,
                class_level=int(klass),
                gender_scope=gender,
            ).first()
        )
        if cat:
            return cat

    # --- Exact age youth (14M, 16F, 18M) ---
    m = AGE_RE.match(raw)
    if m:
        age, gender = m.groups()
        gender = gender.upper()
        age = int(age)
        cat = (
            PlayerCategory.objects.filter(
                taxonomy=PlayerCategory.TAXONOMY_CBT_AGE,
                code__iexact=f'{age}{gender}',
            ).first()
            or PlayerCategory.objects.filter(
                taxonomy=PlayerCategory.TAXONOMY_FPT_AGE,
                code__iexact=f'{age}{gender}',
            ).first()
            or PlayerCategory.objects.filter(
                min_age=age, max_age=age, gender_scope=gender,
            ).first()
        )
        if cat:
            return cat

    # --- Seniors (35+, 40+, 45+) ---
    m = SENIORS_RE.match(raw)
    if m:
        age_str, gender = m.groups()
        gender = (gender or '*').upper()
        age = int(age_str)
        cat = PlayerCategory.objects.filter(
            taxonomy=PlayerCategory.TAXONOMY_SENIORS,
            min_age=age,
            gender_scope__in=[gender, '*'],
        ).first()
        if cat:
            return cat

    # --- Kids ---
    if KIDS_RE.match(raw):
        cat = PlayerCategory.objects.filter(taxonomy=PlayerCategory.TAXONOMY_KIDS).first()
        if cat:
            return cat

    # --- Open ---
    if OPEN_RE.match(raw):
        cat = PlayerCategory.objects.filter(taxonomy=PlayerCategory.TAXONOMY_OPEN).first()
        if cat:
            return cat

    return None


def clear_cache():
    normalize_category_text.cache_clear()
