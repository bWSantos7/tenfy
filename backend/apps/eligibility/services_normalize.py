"""
Maps raw category strings from sources (e.g. '4M1', '14F', '35+', 'BS 14',
'GS 12', 'Duplas 14', 'Sub 16', '16 anos', 'Open Masc.')
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

# Extended patterns for COSAT/ITF-style and Brazilian federation formats
# "BS 14", "GS 12", "BD 16", "GD 12", "XD 14", "MS 18", "WS 16"
ITF_BOYS_RE  = re.compile(r'^\s*(?:BS|BB|MS|BD|MD)\s*(\d{1,2})\s*$', re.IGNORECASE)
ITF_GIRLS_RE = re.compile(r'^\s*(?:GS|GG|WS|GD|WD)\s*(\d{1,2})\s*$', re.IGNORECASE)
ITF_MIXED_RE = re.compile(r'^\s*(?:XD|MX|AD)\s*(\d{1,2})\s*$', re.IGNORECASE)
# "Sub 16", "Sub16", "Sub-16"
SUB_RE = re.compile(r'^\s*[Ss]ub[-\s]*(\d{1,2})\s*([MF])?\s*$', re.IGNORECASE)
# "16 anos", "14 Anos M"
ANOS_RE = re.compile(r'^\s*(\d{1,2})\s*[Aa]nos?\s*([MF])?\s*$', re.IGNORECASE)
# "Duplas 14", "Dupla 12", "Duplas M 14", "Duplas F 12"
DUPLAS_RE = re.compile(
    r'^\s*[Dd]uplas?\s*(?:([MF])(?:asc(?:ulino)?|em(?:inino)?)?)?\s*(\d{1,2})\s*$',
    re.IGNORECASE,
)


def _gender(match_groups, default='*'):
    for g in match_groups:
        if g and g.upper() in ('M', 'F'):
            return g.upper()
    return default


def _find_age_cat(age: int, gender_str: str) -> Optional['PlayerCategory']:
    """Look up a PlayerCategory by max_age + gender with progressively looser criteria."""
    from apps.players.models import PlayerCategory as PC
    age_taxonomies = [PC.TAXONOMY_CBT_AGE, PC.TAXONOMY_FPT_AGE]
    # 1. Exact gender match
    if gender_str not in ('*', ''):
        cat = PC.objects.filter(
            taxonomy__in=age_taxonomies, max_age=age, gender_scope=gender_str
        ).first()
        if cat:
            return cat
    # 2. Any-gender match (gender_scope='*')
    cat = PC.objects.filter(
        taxonomy__in=age_taxonomies, max_age=age, gender_scope='*'
    ).first()
    if cat:
        return cat
    # 3. Any category with matching max_age (gender-agnostic fallback)
    return PC.objects.filter(taxonomy__in=age_taxonomies, max_age=age).first()


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

    # --- ITF-style boys: BS 14, BD 16, MS 18 ---
    m = ITF_BOYS_RE.match(raw)
    if m:
        age = int(m.group(1))
        cat = _find_age_cat(age, 'M')
        if cat:
            return cat

    # --- ITF-style girls: GS 12, WS 14, GD 16 ---
    m = ITF_GIRLS_RE.match(raw)
    if m:
        age = int(m.group(1))
        cat = _find_age_cat(age, 'F')
        if cat:
            return cat

    # --- ITF-style mixed doubles: XD 14, AD 12 ---
    m = ITF_MIXED_RE.match(raw)
    if m:
        age = int(m.group(1))
        cat = _find_age_cat(age, '*')
        if cat:
            return cat

    # --- Sub N: Sub 16, Sub16, Sub-14 M ---
    m = SUB_RE.match(raw)
    if m:
        age = int(m.group(1))
        gender_str = (m.group(2) or '*').upper()
        cat = _find_age_cat(age, gender_str)
        if cat:
            return cat

    # --- N anos: 16 anos, 14 Anos M ---
    m = ANOS_RE.match(raw)
    if m:
        age = int(m.group(1))
        gender_str = (m.group(2) or '*').upper()
        cat = _find_age_cat(age, gender_str)
        if cat:
            return cat

    # --- Duplas N: Duplas 14, Dupla 12, Duplas M 14, Duplas F 12 ---
    m = DUPLAS_RE.match(raw)
    if m:
        gender_str = (m.group(1) or '*').upper()
        age = int(m.group(2))
        cat = _find_age_cat(age, gender_str)
        if cat:
            return cat

    return None


def clear_cache():
    normalize_category_text.cache_clear()
