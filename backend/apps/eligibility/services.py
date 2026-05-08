"""
Eligibility engine.

Evaluates whether a PlayerProfile is compatible with a tournament category,
producing (compatible | incompatible | unknown) + reasons.

MVP rules (per product spec):

1. CBT / FPT age by civil year: sporting_age = current_year - birth_year
   (never uses month/day). Source: CBT Regulamento Infantojuvenil.

2. Youth age rule: player is compatible with any category whose max_age >= player's
   sporting_age. E.g., a 12-year-old is compatible with BS 12, BS 14, BS 16, BS 18.
   A 14-year-old is NOT compatible with a BS 12 category.

3. FPT classes (1..5): Class information is PRESERVED and DISPLAYED, but does NOT
   block MVP compatibility. Categories with only class info return STATUS_UNKNOWN
   with a note to check the official regulations. Per spec: class is informational only.

4. Seniors (35+, 40+, 45+, 50+, ...): unidirectional descending. A 45-year-old
   may enter 35+ but not 50+.

5. Gender match on category scope (M / F / X mixed / * any).

6. When the category has no normalized taxonomy: extract age from raw text as fallback.
   If age found and player's sporting_age <= extracted max_age → compatible.
   If no age found → STATUS_UNKNOWN with safe message.

7. Ranking, competitive level and class do NOT block MVP compatibility.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from apps.players.models import PlayerCategory, PlayerProfile
from apps.tournaments.models import TournamentCategory, TournamentEdition


STATUS_COMPATIBLE = 'compatible'
STATUS_INCOMPATIBLE = 'incompatible'
STATUS_UNKNOWN = 'unknown'

REASON_AGE_OUT = 'age_out_of_range'
REASON_GENDER_MISMATCH = 'gender_mismatch'
REASON_CLASS_TOO_LOW = 'class_too_low'
REASON_CLASS_TOO_HIGH = 'class_too_high'
REASON_NO_BIRTH_YEAR = 'no_birth_year'
REASON_NO_GENDER = 'no_gender'
REASON_NO_CLASS = 'no_class'
REASON_NO_RULE = 'no_rule_available'
REASON_NOT_NORMALIZED = 'category_not_normalized'
REASON_MATCH = 'matches_profile'
REASON_CLASS_INFO_ONLY = 'class_informational_only'

# Extended patterns for raw age extraction from unnormalized category text.
# Order matters: more specific patterns first.
_RAW_AGE_PATTERNS = [
    # ITF-style: BS 14, GS 12, BD 16, GD 12, XD 14, MS 18, WS 16
    (re.compile(r'^\s*(?P<pfx>BS|BB|MS|BD|MD)\s*(?P<age>\d{1,2})\s*$', re.I), 'M'),
    (re.compile(r'^\s*(?P<pfx>GS|GG|WS|GD|WD)\s*(?P<age>\d{1,2})\s*$', re.I), 'F'),
    (re.compile(r'^\s*(?P<pfx>XD|MX|AD)\s*(?P<age>\d{1,2})\s*$', re.I), '*'),
    # Duplas gender-age: "Duplas M 14", "Duplas F 12"
    (re.compile(r'^\s*[Dd]uplas?\s*M(?:asc(?:ulino)?)?\s*(?P<age>\d{1,2})\s*$', re.I), 'M'),
    (re.compile(r'^\s*[Dd]uplas?\s*F(?:em(?:inino)?)?\s*(?P<age>\d{1,2})\s*$', re.I), 'F'),
    # Duplas age only: "Duplas 14", "Dupla 12"
    (re.compile(r'^\s*[Dd]uplas?\s*(?P<age>\d{1,2})\s*$', re.I), '*'),
    # Sub N (with optional gender): "Sub 16", "Sub16", "Sub-16 M"
    (re.compile(r'^\s*[Ss]ub[-\s]*(?P<age>\d{1,2})\s*(?P<g>[MF])?\s*$', re.I), None),
    # N anos (with optional gender): "16 anos", "14 Anos M"
    (re.compile(r'^\s*(?P<age>\d{1,2})\s*[Aa]nos?\s*(?P<g>[MF])?\s*$', re.I), None),
    # Plain "14M", "12F" — already handled by normalizer but as fallback
    (re.compile(r'^\s*(?P<age>\d{1,2})\s*(?P<g>[MF])\s*$', re.I), None),
]

# Ranking check states (informational — do not flip the main eligibility status).
RANKING_NOT_APPLICABLE = 'not_applicable'   # Categoria sem max_participants
RANKING_UNKNOWN = 'unknown'                 # Sem dados suficientes para confirmar
RANKING_WITHIN_CUTOFF = 'within_cutoff'     # Ranking do perfil dentro do corte estimado
RANKING_BEYOND_CUTOFF = 'beyond_cutoff'     # Ranking do perfil acima do corte estimado


@dataclass
class EligibilityResult:
    status: str
    reasons: list = field(default_factory=list)
    rule_version_id: Optional[int] = None
    category_code: Optional[str] = None
    category_label: Optional[str] = None
    # Ranking metadata — informational only. Spec: "Não inventar elegibilidade".
    ranking_check: str = RANKING_NOT_APPLICABLE
    ranking_note: str = ''

    def to_dict(self):
        return {
            'status': self.status,
            'reasons': self.reasons,
            'rule_version_id': self.rule_version_id,
            'category_code': self.category_code,
            'category_label': self.category_label,
            'ranking_check': self.ranking_check,
            'ranking_note': self.ranking_note,
        }


class EligibilityEngine:
    """Evaluate a player profile against tournament categories."""

    def __init__(self, profile: PlayerProfile):
        self.profile = profile
        self._current_year = datetime.now().year

    @property
    def sporting_age(self) -> Optional[int]:
        if self.profile.birth_year:
            return self._current_year - self.profile.birth_year
        return None

    # ---------- Category evaluation ----------

    @staticmethod
    def extract_age_from_text(text: str) -> Optional[tuple]:
        """Extract (max_age: int, gender: str) from raw category text.
        Returns None if no numeric age can be extracted.
        Gender is 'M', 'F', or '*' (any/unknown)."""
        raw = (text or '').strip()
        for pattern, fixed_gender in _RAW_AGE_PATTERNS:
            m = pattern.match(raw)
            if m:
                age = int(m.group('age'))
                if fixed_gender is not None:
                    gender = fixed_gender
                else:
                    try:
                        g = m.group('g')
                        gender = g.upper() if g else '*'
                    except IndexError:
                        gender = '*'
                return age, gender
        return None

    def evaluate_category(self, tc: TournamentCategory) -> EligibilityResult:
        """Evaluate a single TournamentCategory against the player."""
        norm: Optional[PlayerCategory] = tc.normalized_category
        if norm is None:
            # Try extracting age directly from the raw category text (e.g. "BS 14", "Duplas 12")
            raw_age = self.extract_age_from_text(tc.source_category_text)
            if raw_age is not None:
                max_age, gender = raw_age
                base = self._evaluate_raw_age(tc.source_category_text, max_age, gender)
            else:
                base = EligibilityResult(
                    status=STATUS_UNKNOWN,
                    reasons=[REASON_NOT_NORMALIZED],
                    category_code=tc.source_category_text,
                    category_label=tc.source_category_text,
                )
        else:
            base = self.evaluate_player_category(
                norm,
                source_text=tc.source_category_text,
            )

        # Ranking metadata (informational, never flips main status to compatible).
        rank_check, rank_note = self._check_ranking(tc)
        base.ranking_check = rank_check
        base.ranking_note = rank_note
        return base

    def evaluate_player_category(
        self, cat: PlayerCategory, source_text: Optional[str] = None
    ) -> EligibilityResult:
        reasons = []

        # --- gender check ---
        gender_ok = self._check_gender(cat, reasons)

        # --- taxonomy-specific logic ---
        taxonomy_status = self._check_taxonomy(cat, reasons)

        # Combine
        if taxonomy_status == STATUS_UNKNOWN:
            status = STATUS_UNKNOWN
        elif not gender_ok:
            status = STATUS_INCOMPATIBLE
        elif taxonomy_status == STATUS_COMPATIBLE:
            status = STATUS_COMPATIBLE
            reasons.append(REASON_MATCH)
        else:
            status = STATUS_INCOMPATIBLE

        return EligibilityResult(
            status=status,
            reasons=list(set(reasons)),
            category_code=cat.code,
            category_label=cat.label_ptbr,
        )

    # ---------- Helpers ----------

    def _check_gender(self, cat: PlayerCategory, reasons: list) -> bool:
        gs = cat.gender_scope
        if gs in ('*', 'X'):
            return True
        if not self.profile.gender:
            reasons.append(REASON_NO_GENDER)
            return True  # unknown gender treated as soft-pass
        return gs == self.profile.gender

    def _check_taxonomy(self, cat: PlayerCategory, reasons: list) -> str:
        t = cat.taxonomy

        if t == PlayerCategory.TAXONOMY_FPT_CLASS:
            return self._check_fpt_class(cat, reasons)

        if t in (PlayerCategory.TAXONOMY_FPT_AGE, PlayerCategory.TAXONOMY_CBT_AGE,
                 PlayerCategory.TAXONOMY_KIDS):
            return self._check_exact_age(cat, reasons)

        if t == PlayerCategory.TAXONOMY_SENIORS:
            return self._check_seniors(cat, reasons)

        if t == PlayerCategory.TAXONOMY_OPEN:
            return STATUS_COMPATIBLE

        reasons.append(REASON_NO_RULE)
        return STATUS_UNKNOWN

    def _check_fpt_class(self, cat: PlayerCategory, reasons: list) -> str:
        # MVP rule: class is informational only — does NOT block compatibility.
        # Class data is preserved and displayed, but never used to exclude a player.
        # Players should verify class eligibility directly with the official regulations.
        reasons.append(REASON_CLASS_INFO_ONLY)
        return STATUS_UNKNOWN

    def _evaluate_raw_age(self, source_text: str, max_age: int, gender: str) -> EligibilityResult:
        """Evaluate compatibility based on age extracted from raw category text.
        Rule: player's sporting_age must be <= max_age (younger players can enter older categories)."""
        reasons = []
        # Gender check
        if gender not in ('*', 'X') and self.profile.gender and gender != self.profile.gender:
            reasons.append(REASON_GENDER_MISMATCH)
            return EligibilityResult(
                status=STATUS_INCOMPATIBLE,
                reasons=reasons,
                category_code=source_text,
                category_label=source_text,
            )
        # Age check
        age = self.sporting_age
        if age is None:
            return EligibilityResult(
                status=STATUS_UNKNOWN,
                reasons=[REASON_NO_BIRTH_YEAR],
                category_code=source_text,
                category_label=source_text,
            )
        if age <= max_age:
            return EligibilityResult(
                status=STATUS_COMPATIBLE,
                reasons=[REASON_MATCH],
                category_code=source_text,
                category_label=source_text,
            )
        reasons.append(REASON_AGE_OUT)
        return EligibilityResult(
            status=STATUS_INCOMPATIBLE,
            reasons=reasons,
            category_code=source_text,
            category_label=source_text,
        )

    def _check_exact_age(self, cat: PlayerCategory, reasons: list) -> str:
        """Youth age check: player's sporting_age must be <= category's max_age.
        A 12-year-old can enter BS 12, BS 14, BS 16, BS 18, but NOT BS 10."""
        age = self.sporting_age
        if age is None:
            reasons.append(REASON_NO_BIRTH_YEAR)
            return STATUS_UNKNOWN
        max_age = cat.max_age
        if max_age is not None:
            if age <= max_age:
                return STATUS_COMPATIBLE
            reasons.append(REASON_AGE_OUT)
            return STATUS_INCOMPATIBLE
        # Fallback to min_age only (e.g. "18+" open-ended categories)
        min_age = cat.min_age
        if min_age is not None and age >= min_age:
            return STATUS_COMPATIBLE
        reasons.append(REASON_NO_RULE)
        return STATUS_UNKNOWN

    def _profile_ranking(self) -> Optional[int]:
        """Read the player's known ranking from PlayerProfile.external_ids.
        Looked-up keys (first match wins): cbt_ranking, fpt_ranking, ranking, ranking_position.
        Must be a positive integer; anything else is treated as unknown."""
        ext = getattr(self.profile, 'external_ids', None) or {}
        if not isinstance(ext, dict):
            return None
        for key in ('cbt_ranking', 'fpt_ranking', 'ranking_position', 'ranking'):
            val = ext.get(key)
            if val is None:
                continue
            try:
                rank = int(val)
                if rank > 0:
                    return rank
            except (TypeError, ValueError):
                continue
        return None

    def _check_ranking(self, tc: TournamentCategory) -> tuple:
        """
        Conservative ranking check. Returns (status, note).

        Rule: only flag 'within_cutoff' / 'beyond_cutoff' when the data is solid:
          - category has max_participants set
          - profile has a known ranking value
          - at least max_participants FederationEntry rows with ranking_position
        Otherwise: 'unknown' (with explanatory note) or 'not_applicable'.

        We never use this to mark the main status compatible/incompatible — only
        as informational metadata. Per spec: "Não inventar elegibilidade."
        """
        max_p = tc.max_participants
        if not max_p:
            return RANKING_NOT_APPLICABLE, ''

        profile_rank = self._profile_ranking()
        if profile_rank is None:
            return RANKING_UNKNOWN, 'Ranking do perfil não informado.'

        from apps.registrations.models import FederationEntry
        entries = (
            FederationEntry.objects
            .filter(
                edition_id=tc.edition_id,
                category_text__iexact=tc.source_category_text,
                ranking_position__isnull=False,
                removed_or_replaced=False,
            )
            .order_by('ranking_position')
            .values_list('ranking_position', flat=True)[:max_p]
        )
        ranking_list = list(entries)
        if len(ranking_list) < max_p:
            return RANKING_UNKNOWN, 'Lista de inscritos incompleta — corte de ranking não estimado.'

        cutoff = ranking_list[-1]
        if profile_rank <= cutoff:
            return RANKING_WITHIN_CUTOFF, f'Ranking dentro do corte estimado ({cutoff}).'
        return RANKING_BEYOND_CUTOFF, f'Ranking acima do corte estimado ({cutoff}). Vaga incerta — confirme inscrição oficial.'

    def _check_seniors(self, cat: PlayerCategory, reasons: list) -> str:
        """Seniors: player age must be >= category min_age (descending allowed)."""
        age = self.sporting_age
        if age is None:
            reasons.append(REASON_NO_BIRTH_YEAR)
            return STATUS_UNKNOWN
        if cat.min_age is None:
            reasons.append(REASON_NO_RULE)
            return STATUS_UNKNOWN
        if age >= cat.min_age:
            return STATUS_COMPATIBLE
        reasons.append(REASON_AGE_OUT)
        return STATUS_INCOMPATIBLE

    # ---------- Edition summary ----------

    def evaluate_edition(self, edition: TournamentEdition) -> dict:
        results = []
        compatible_count = 0
        incompatible_count = 0
        unknown_count = 0
        for tc in edition.categories.select_related('normalized_category').all():
            r = self.evaluate_category(tc)
            results.append({
                'tournament_category_id': tc.id,
                'source_text': tc.source_category_text,
                'result': r.to_dict(),
                'price_brl': str(tc.price_brl) if tc.price_brl is not None else None,
            })
            if r.status == STATUS_COMPATIBLE:
                compatible_count += 1
            elif r.status == STATUS_INCOMPATIBLE:
                incompatible_count += 1
            else:
                unknown_count += 1

        # effective_compatible: a tournament is "effectively compatible" if it has
        # at least one compatible category, OR has no incompatible categories at all
        # (class-only or unclassified tournaments should not be excluded by default).
        effective_compatible = compatible_count > 0 or (incompatible_count == 0 and unknown_count > 0)

        return {
            'edition_id': edition.id,
            'profile_id': self.profile.id,
            'sporting_age': self.sporting_age,
            'total_count': len(results),
            'compatible_count': compatible_count,
            'incompatible_count': incompatible_count,
            'unknown_count': unknown_count,
            'effective_compatible': effective_compatible,
            'categories': results,
        }
