"""
Maps raw category strings from sources to canonical PlayerCategory rows.
Falls back to None → result unknown.

Supported formats:
  FPT class    : "4M", "3F1", "2M2" etc.
  Age youth    : "14M", "16F", "12M" etc.
  Seniors      : "35+", "40+M" etc.
  Kids         : "kids", "red ball" etc.
  Open         : "open", "adulto" etc.
  COSAT/ITF    : "BS U12", "GS U14", "BD 16", "GD 18", "BSU14",
                 "Boys Singles U12", "Girls Doubles U18" etc.
  Duplas text  : "Dupla Masculina - 12 anos", "Dupla Feminina - 16 anos" etc.
  Simples text : "Simples Masculino - 14 anos", "Simples Feminino - 18 anos"
"""
import re
import logging
from functools import lru_cache
from typing import Optional

from apps.players.models import PlayerCategory

logger = logging.getLogger('apps.eligibility.normalize')


# ── Existing patterns ──────────────────────────────────────────────────────────

CLASS_RE = re.compile(r'^\s*([1-5])\s*([MF])\s*([12])?\s*$', re.IGNORECASE)
AGE_RE = re.compile(r'^\s*(\d{1,2})\s*([MF])\s*$', re.IGNORECASE)
SENIORS_RE = re.compile(r'^\s*(\d{2})\+\s*([MF])?\s*$')
KIDS_RE = re.compile(r'^(?:kids?|red|orange|green|yellow|ball\d+)\s*([MF])?\s*$', re.IGNORECASE)
OPEN_RE = re.compile(r'^(?:open|principal|adulto|absoluto)\s*([MF])?\s*$', re.IGNORECASE)

# ── COSAT / ITF patterns ───────────────────────────────────────────────────────

# Canonical two-letter codes: BS, GS, BD, GD (with or without space before U/age)
_COSAT_CODE_RE = re.compile(
    r'^\s*(BS|GS|BD|GD)\s*[Uu]?\s*(\d{1,2})\s*$',
    re.IGNORECASE,
)

# Full English name: "Boys Singles U12", "Girls Doubles 14", etc.
_COSAT_FULL_RE = re.compile(
    r'^\s*(boys?|girls?)\s+(singles?|doubles?)\s*[Uu]?\s*(\d{1,2})\s*$',
    re.IGNORECASE,
)

# Without separator: BSU12, GSU14, BDU16, GDU18
_COSAT_NOSPACE_RE = re.compile(
    r'^\s*(BS|GS|BD|GD)[Uu](\d{1,2})\s*$',
    re.IGNORECASE,
)

# ── Duplas / Simples texto português ──────────────────────────────────────────

_DUPLAS_MASC_RE = re.compile(
    r'dupla[s]?\s+masculin[ao]s?\s*[-–]?\s*(\d{1,2})\s*(?:anos?)?',
    re.IGNORECASE,
)
_DUPLAS_FEM_RE = re.compile(
    r'dupla[s]?\s+feminin[ao]s?\s*[-–]?\s*(\d{1,2})\s*(?:anos?)?',
    re.IGNORECASE,
)
_SIMPLES_MASC_RE = re.compile(
    r'simples\s+masculin[ao]s?\s*[-–]?\s*(\d{1,2})\s*(?:anos?)?',
    re.IGNORECASE,
)
_SIMPLES_FEM_RE = re.compile(
    r'simples\s+feminin[ao]s?\s*[-–]?\s*(\d{1,2})\s*(?:anos?)?',
    re.IGNORECASE,
)

# Generic "N anos" (e.g. "16 anos", "Sub 14") — no gender
_ANOS_RE = re.compile(r'(?:sub\s*[-–]?\s*)?(\d{1,2})\s*anos?', re.IGNORECASE)
_U_AGE_RE = re.compile(r'\bU\s*(\d{1,2})\b', re.IGNORECASE)


def _gender(match_groups, default='*'):
    for g in match_groups:
        if g and g.upper() in ('M', 'F'):
            return g.upper()
    return default


def _cosat_gender_from_code(code: str) -> str:
    """BS/BD → 'M'; GS/GD → 'F'"""
    return 'M' if code[0].upper() == 'B' else 'F'


def _find_age_cat(max_age: int, gender: str) -> Optional[PlayerCategory]:
    """Find a PlayerCategory by max_age, with gender fallback chain."""
    # 1. Exact gender match in CBT/FPT/KIDS taxonomies
    qs = PlayerCategory.objects.filter(
        max_age=max_age,
        taxonomy__in=[
            PlayerCategory.TAXONOMY_CBT_AGE,
            PlayerCategory.TAXONOMY_FPT_AGE,
            PlayerCategory.TAXONOMY_KIDS,
        ],
    )
    if gender in ('M', 'F'):
        cat = qs.filter(gender_scope=gender).first()
        if cat:
            return cat
        # 2. Wildcard gender ('*')
        cat = qs.filter(gender_scope='*').first()
        if cat:
            return cat
        # Do not fall through to a wrong-gender row — caller preserves the
        # gender extracted from the raw text and passes it to _check_raw_age_gender.
        return None
    # gender is '*' or unspecified — any match is acceptable
    cat = qs.first()
    if cat:
        return cat
    return PlayerCategory.objects.filter(max_age=max_age).first()


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
            or _find_age_cat(age, gender)
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

    # --- COSAT/ITF: BSU12, BS U12, Boys Singles U12 ---
    m = _COSAT_NOSPACE_RE.match(raw) or _COSAT_CODE_RE.match(raw)
    if m:
        code_part, age_str = m.group(1), m.group(2)
        gender = _cosat_gender_from_code(code_part)
        age = int(age_str)
        cat = _find_age_cat(age, gender)
        if cat:
            return cat

    m = _COSAT_FULL_RE.match(raw)
    if m:
        boy_girl, _singles_doubles, age_str = m.groups()
        gender = 'M' if boy_girl[0].lower() == 'b' else 'F'
        age = int(age_str)
        cat = _find_age_cat(age, gender)
        if cat:
            return cat

    # --- Dupla Masculina/Feminina - N anos ---
    m = _DUPLAS_MASC_RE.search(raw)
    if m:
        cat = _find_age_cat(int(m.group(1)), 'M')
        if cat:
            return cat

    m = _DUPLAS_FEM_RE.search(raw)
    if m:
        cat = _find_age_cat(int(m.group(1)), 'F')
        if cat:
            return cat

    # --- Simples Masculino/Feminino - N anos ---
    m = _SIMPLES_MASC_RE.search(raw)
    if m:
        cat = _find_age_cat(int(m.group(1)), 'M')
        if cat:
            return cat

    m = _SIMPLES_FEM_RE.search(raw)
    if m:
        cat = _find_age_cat(int(m.group(1)), 'F')
        if cat:
            return cat

    # --- Generic "N anos" / "Sub N" / "U N" ---
    m = _ANOS_RE.search(raw)
    if m:
        cat = _find_age_cat(int(m.group(1)), '*')
        if cat:
            return cat

    m = _U_AGE_RE.search(raw)
    if m:
        cat = _find_age_cat(int(m.group(1)), '*')
        if cat:
            return cat

    return None


def clear_cache():
    normalize_category_text.cache_clear()
