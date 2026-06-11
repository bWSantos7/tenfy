"""
Eligibility engine.

Evaluates whether a PlayerProfile is compatible with a tournament category,
producing (compatible | incompatible | unknown) + reasons.

Rules implemented (faithful to the source regulations):

1. CBT / FPT age by civil year: sporting_age = current_year - birth_year
   (never uses month/day). Source: CBT Regulamento Infantojuvenil.

2. FPT classes (1..5): a player in class N may also enter class N-1
   (one class above, strict harder direction). A 5th-class player may
   play 4th class. A 5th-class player may NOT play 3rd class.
   A 1st-class player may NOT descend to 2nd class.

3. Seniors (35+, 40+, 45+, 50+, ...): unidirectional descending. A 45-year-old
   may enter 35+ but not 50+.

4. Youth age categories (12, 14, 16, 18, etc.): player must be <= max_age.
   "14 anos" = up to 14 years old — a 12-year-old qualifies. A 15-year-old does not.

5. Gender match on category scope (M / F / X mixed / * any).

6. When the category has no normalized taxonomy or no rule found, status is
   'unknown' with reason 'no_rule_available'.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from django.utils import timezone

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
REASON_COSAT_RANKING_REQUIRED = 'cosat_ranking_required'
REASON_ITF_RANKING_REQUIRED = 'itf_ranking_required'
REASON_CATEGORY_ABOVE_LIMIT = 'category_above_circuit_limit'
REASON_CATEGORY_UNAVAILABLE = 'category_unavailable_for_circuit'

YOUTH_CATEGORY_BUCKETS = (10, 12, 14, 16, 18)
CIRCUIT_PAULISTA = 'paulista'
CIRCUIT_BRASILEIRO = 'brasileiro'
CIRCUIT_COSAT = 'cosat'
CIRCUIT_ITF = 'itf'
SUPPORTED_YOUTH_CIRCUITS = {
    CIRCUIT_PAULISTA,
    CIRCUIT_BRASILEIRO,
    CIRCUIT_COSAT,
    CIRCUIT_ITF,
}

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


def official_youth_category_age(profile: PlayerProfile) -> Optional[int]:
    """
    Return the player's official youth category age.

    Prefer the sporting age because the youth official category is derived from
    civil year. Fall back to a declared primary age category only when the birth
    year is unavailable.
    """
    sporting_age = getattr(profile, 'sporting_age', None)
    if sporting_age is None and getattr(profile, 'birth_year', None):
        sporting_age = timezone.now().year - profile.birth_year
    if sporting_age is not None:
        for bucket in YOUTH_CATEGORY_BUCKETS:
            if sporting_age <= bucket:
                return bucket
        return None

    categories_rel = getattr(profile, 'profile_categories', None)
    if categories_rel is not None and hasattr(categories_rel, 'select_related'):
        declared = (
            categories_rel
            .select_related('category')
            .filter(
                category__taxonomy__in=[
                    PlayerCategory.TAXONOMY_CBT_AGE,
                    PlayerCategory.TAXONOMY_FPT_AGE,
                    PlayerCategory.TAXONOMY_KIDS,
                ],
                category__max_age__isnull=False,
            )
            .order_by('-is_primary', 'category__max_age')
            .first()
        )
        if declared and declared.category.max_age:
            return declared.category.max_age

    return None


def classify_tournament_circuit(edition: TournamentEdition) -> Optional[str]:
    """Map a tournament edition to the circuit policy used by youth category rules."""
    tournament = getattr(edition, 'tournament', None)
    org = getattr(tournament, 'organization', None)
    org_short = (getattr(org, 'short_name', '') or '').upper()
    org_name = (getattr(org, 'name', '') or '').upper()
    circuit = (getattr(tournament, 'circuit', '') or '').upper()
    title = (getattr(edition, 'title', '') or '').upper()
    external_id = (getattr(edition, 'external_id', '') or '').lower()

    if (
        external_id.startswith('itf:')
        or org_short == 'ITF'
        or 'INTERNATIONAL TENNIS FEDERATION' in org_name
        or 'ITF' in circuit
        or ('ITF' in title and ('JUNIOR' in title or 'JUVENIL' in title))
    ):
        return CIRCUIT_ITF
    if (
        external_id.startswith('cosat:')
        or org_short == 'COSAT'
        or 'COSAT' in org_name
        or 'COSAT' in circuit
        or 'COSAT' in title
    ):
        return CIRCUIT_COSAT
    if org_short == 'CBT' or 'CONFEDERACAO BRASILEIRA' in org_name or 'BRASILEIRA DE TENIS' in org_name:
        return CIRCUIT_BRASILEIRO
    if (
        org_short in ('FPT', 'FPT-SP')   # sigla oficial é FPT-SP (TASK 1)
        or 'PAULISTA' in org_name        # robusto à acentuação (Ç/Ã)
        or 'PAULISTA' in circuit
    ):
        return CIRCUIT_PAULISTA
    return None


def allowed_youth_category_ages(
    profile: PlayerProfile,
    edition: TournamentEdition,
    include_category_up: bool = True,
) -> Optional[set[int]]:
    """Return allowed youth category ages for the profile and tournament circuit."""
    official_age = official_youth_category_age(profile)
    if official_age is None:
        return None

    if not include_category_up:
        return {official_age}

    circuit = classify_tournament_circuit(edition)
    if circuit == CIRCUIT_PAULISTA:
        start = YOUTH_CATEGORY_BUCKETS.index(official_age) if official_age in YOUTH_CATEGORY_BUCKETS else None
        if start is None:
            return {official_age}
        return set(YOUTH_CATEGORY_BUCKETS[start:start + 3])
    if circuit == CIRCUIT_BRASILEIRO:
        start = YOUTH_CATEGORY_BUCKETS.index(official_age) if official_age in YOUTH_CATEGORY_BUCKETS else None
        if start is None:
            return {official_age}
        return set(YOUTH_CATEGORY_BUCKETS[start:start + 2])
    if circuit == CIRCUIT_COSAT:
        start = YOUTH_CATEGORY_BUCKETS.index(official_age) if official_age in YOUTH_CATEGORY_BUCKETS else None
        if start is None:
            return set()
        return set(YOUTH_CATEGORY_BUCKETS[start:start + 2]) & {14, 16}
    if circuit == CIRCUIT_ITF:
        return {18}

    sporting_age = getattr(profile, 'sporting_age', None)
    if sporting_age is None and getattr(profile, 'birth_year', None):
        sporting_age = timezone.now().year - profile.birth_year
    if sporting_age is None:
        return None
    return {age for age in YOUTH_CATEGORY_BUCKETS if age >= sporting_age}


class EligibilityEngine:
    """Evaluate a player profile against tournament categories."""

    def __init__(self, profile: PlayerProfile, include_category_up: bool = False):
        self.profile = profile
        self.include_category_up = include_category_up
        self._current_year = timezone.now().year

    @property
    def sporting_age(self) -> Optional[int]:
        if self.profile.birth_year:
            return self._current_year - self.profile.birth_year
        return None

    # ---------- Category evaluation ----------

    def evaluate_category(self, tc: TournamentCategory) -> EligibilityResult:
        """Evaluate a single TournamentCategory against the player."""
        norm: Optional[PlayerCategory] = tc.normalized_category
        if norm is None:
            # Try raw text extraction for COSAT/duplas/unnormalized categories
            forced_age = 18 if classify_tournament_circuit(tc.edition) == CIRCUIT_ITF else None
            base = self._evaluate_raw_text(tc.source_category_text, forced_age=forced_age)
        else:
            base = self.evaluate_player_category(
                norm,
                source_text=tc.source_category_text,
            )
        base = self._apply_tournament_youth_policy(tc, base)

        # Ranking metadata (informational, never flips main status to compatible).
        rank_check, rank_note = self._check_ranking(tc)
        base.ranking_check = rank_check
        base.ranking_note = rank_note
        return base

    def _extract_raw_age_gender(self, text: str, forced_age: Optional[int] = None) -> tuple[Optional[int], Optional[str]]:
        """
        Extract (max_age, gender) from COSAT/ITF codes, duplas/simples text,
        and generic age labels.
        """
        import re as _re

        if not text:
            return forced_age, None

        raw = text.strip()

        # COSAT compact: BS U12, GS U14, BD16, GDU18, BSU12 …
        _COSAT_CODE = _re.compile(
            r'^\s*(BS|GS|BD|GD)\s*[Uu]?\s*(\d{1,2})\s*$', _re.IGNORECASE
        )
        _COSAT_NOSPACE = _re.compile(
            r'^\s*(BS|GS|BD|GD)[Uu](\d{1,2})\s*$', _re.IGNORECASE
        )
        _COSAT_FULL = _re.compile(
            r'^\s*(boys?|girls?)\s+(singles?|doubles?)\s*[Uu]?\s*(\d{1,2})\s*$',
            _re.IGNORECASE,
        )
        _DUPLAS_M = _re.compile(
            r'dupla[s]?\s+masculin[ao]s?\s*[-–]?\s*(\d{1,2})\s*(?:anos?)?', _re.IGNORECASE
        )
        _DUPLAS_F = _re.compile(
            r'dupla[s]?\s+feminin[ao]s?\s*[-–]?\s*(\d{1,2})\s*(?:anos?)?', _re.IGNORECASE
        )
        _SIMPLES_M = _re.compile(
            r'simples\s+masculin[ao]s?\s*[-–]?\s*(\d{1,2})\s*(?:anos?)?', _re.IGNORECASE
        )
        _SIMPLES_F = _re.compile(
            r'simples\s+feminin[ao]s?\s*[-–]?\s*(\d{1,2})\s*(?:anos?)?', _re.IGNORECASE
        )
        _ANOS = _re.compile(r'(?:sub\s*[-–]?\s*)?(\d{1,2})\s*anos?', _re.IGNORECASE)
        # U14, U 14, U-14 (with optional hyphen/dash)
        _U_AGE = _re.compile(r'\bU\s*[-–]?\s*(\d{1,2})\b', _re.IGNORECASE)
        # ITF/federation format: "Sub-18", "sub18", "sub 18" (without "anos")
        _SUB_AGE = _re.compile(r'\bsub\s*[-–]?\s*(\d{1,2})\b', _re.IGNORECASE)
        # Last-resort: bare youth age bucket number, e.g. "14 Masc" or "IJ 14"
        _AGE_BARE = _re.compile(r'\b(10|12|14|16|18)\b')
        _AGE_GENDER_CODE = _re.compile(r'\b(10|12|14|16|18)\s*([MF])\b', _re.IGNORECASE)
        # Gender words — full and abbreviated (Masc, Fem are common FPT/CBT shorthands)
        _MASC = _re.compile(r'\b(masculin[ao]|masc|boys?|male)\b', _re.IGNORECASE)
        _FEM  = _re.compile(r'\b(feminin[ao]|fem|girls?|female)\b', _re.IGNORECASE)

        extracted_age: Optional[int] = forced_age
        extracted_gender: Optional[str] = None  # 'M', 'F', or None = unknown

        if forced_age is None:
            m = _COSAT_NOSPACE.match(raw) or _COSAT_CODE.match(raw)
            if m:
                code_part, age_str = m.group(1), m.group(2)
                extracted_gender = 'M' if code_part[0].upper() == 'B' else 'F'
                extracted_age = int(age_str)
        else:
            m = _COSAT_NOSPACE.match(raw) or _COSAT_CODE.match(raw)
            if m:
                code_part = m.group(1)
                extracted_gender = 'M' if code_part[0].upper() == 'B' else 'F'

        if extracted_age is None:
            m = _COSAT_FULL.match(raw)
            if m:
                boy_girl, _sd, age_str = m.groups()
                extracted_gender = 'M' if boy_girl[0].lower() == 'b' else 'F'
                extracted_age = int(age_str)

        if extracted_age is None:
            m = _DUPLAS_M.search(raw)
            if m:
                extracted_gender = 'M'
                extracted_age = int(m.group(1))

        if extracted_age is None:
            m = _DUPLAS_F.search(raw)
            if m:
                extracted_gender = 'F'
                extracted_age = int(m.group(1))

        if extracted_age is None:
            m = _SIMPLES_M.search(raw)
            if m:
                extracted_gender = 'M'
                extracted_age = int(m.group(1))

        if extracted_age is None:
            m = _SIMPLES_F.search(raw)
            if m:
                extracted_gender = 'F'
                extracted_age = int(m.group(1))

        if extracted_age is None:
            m = _AGE_GENDER_CODE.search(raw)
            if m:
                extracted_age = int(m.group(1))
                extracted_gender = m.group(2).upper()

        if extracted_age is None:
            m = _ANOS.search(raw)
            if m:
                extracted_age = int(m.group(1))

        if extracted_age is None:
            m = _U_AGE.search(raw)
            if m:
                extracted_age = int(m.group(1))

        # "Sub-18", "sub18", "sub 18" (ITF / federation format, no "anos")
        if extracted_age is None:
            m = _SUB_AGE.search(raw)
            if m:
                extracted_age = int(m.group(1))

        # Fallback: bare youth age bucket number with word boundaries.
        # Handles "14 Masc", "IJ 14", "Masculino 14", "Feminino 14 anos" (already
        # caught by _ANOS above, so no double-match), etc.
        if extracted_age is None:
            m = _AGE_BARE.search(raw)
            if m:
                extracted_age = int(m.group(1))

        # Extract gender from "Masculino" / "Feminino" / "Boys" / "Girls" when not yet set
        if extracted_gender is None and extracted_age is not None:
            if _MASC.search(raw):
                extracted_gender = 'M'
            elif _FEM.search(raw):
                extracted_gender = 'F'

        return extracted_age, extracted_gender

    def _evaluate_raw_text(self, text: str, forced_age: Optional[int] = None) -> EligibilityResult:
        """
        Handle COSAT/ITF codes, duplas/simples por texto, and generic age extraction
        for categories that could not be normalized to a PlayerCategory row.

        Extracts (max_age, gender) from the raw text and evaluates directly.
        """
        extracted_age, extracted_gender = self._extract_raw_age_gender(text, forced_age=forced_age)

        if extracted_age is None:
            return EligibilityResult(
                status=STATUS_UNKNOWN,
                reasons=[REASON_NOT_NORMALIZED],
                category_code=text,
                category_label=text,
            )

        return self._check_raw_age_gender(extracted_age, extracted_gender, text)

    def _category_youth_age(self, tc: TournamentCategory) -> Optional[int]:
        norm = tc.normalized_category
        if norm is not None and norm.taxonomy in (
            PlayerCategory.TAXONOMY_FPT_AGE,
            PlayerCategory.TAXONOMY_CBT_AGE,
            PlayerCategory.TAXONOMY_KIDS,
        ):
            return norm.max_age

        forced_age = 18 if classify_tournament_circuit(tc.edition) == CIRCUIT_ITF else None
        extracted_age, _gender = self._extract_raw_age_gender(
            tc.source_category_text,
            forced_age=forced_age,
        )
        return extracted_age

    def _apply_tournament_youth_policy(
        self,
        tc: TournamentCategory,
        result: EligibilityResult,
    ) -> EligibilityResult:
        if result.status != STATUS_COMPATIBLE:
            return result

        category_age = self._category_youth_age(tc)
        if category_age is None:
            return result

        circuit = classify_tournament_circuit(tc.edition)

        # COSAT: only 14 and 16 years are valid categories.
        if circuit == CIRCUIT_COSAT and category_age not in {14, 16}:
            return EligibilityResult(
                status=STATUS_INCOMPATIBLE,
                reasons=list(set(result.reasons + [REASON_CATEGORY_UNAVAILABLE])),
                category_code=result.category_code,
                category_label=result.category_label,
                ranking_check=result.ranking_check,
                ranking_note=result.ranking_note,
            )
        # ITF juvenile: treated as category 18 only.
        if circuit == CIRCUIT_ITF and category_age != 18:
            return EligibilityResult(
                status=STATUS_INCOMPATIBLE,
                reasons=list(set(result.reasons + [REASON_CATEGORY_UNAVAILABLE])),
                category_code=result.category_code,
                category_label=result.category_label,
                ranking_check=result.ranking_check,
                ranking_note=result.ranking_note,
            )

        # Default listing: show ONLY the official category regardless of circuit.
        # Advanced filter (include_category_up=True) applies per-circuit limits below.
        if not self.include_category_up:
            official_age = official_youth_category_age(self.profile)
            if official_age is not None and category_age != official_age:
                return EligibilityResult(
                    status=STATUS_INCOMPATIBLE,
                    reasons=list(set(result.reasons + [REASON_CATEGORY_ABOVE_LIMIT])),
                    category_code=result.category_code,
                    category_label=result.category_label,
                    ranking_check=result.ranking_check,
                    ranking_note=result.ranking_note,
                )
            return result

        # Advanced filter: apply per-circuit promotion limits.
        if circuit in SUPPORTED_YOUTH_CIRCUITS:
            allowed = allowed_youth_category_ages(
                self.profile,
                tc.edition,
                include_category_up=True,
            )
            if allowed is not None and category_age not in allowed:
                return EligibilityResult(
                    status=STATUS_INCOMPATIBLE,
                    reasons=list(set(result.reasons + [REASON_CATEGORY_ABOVE_LIMIT])),
                    category_code=result.category_code,
                    category_label=result.category_label,
                    ranking_check=result.ranking_check,
                    ranking_note=result.ranking_note,
                )
        return result

    def _check_raw_age_gender(
        self, max_age: int, gender: Optional[str], source_text: str = ''
    ) -> EligibilityResult:
        """Evaluate age <= max_age and optional gender against profile."""
        reasons: list = []

        # Gender check
        if gender in ('M', 'F'):
            profile_gender = self.profile.gender
            if not profile_gender:
                reasons.append(REASON_NO_GENDER)
                # soft-pass — unknown gender, don't block
            elif profile_gender != gender:
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
            reasons.append(REASON_NO_BIRTH_YEAR)
            return EligibilityResult(
                status=STATUS_UNKNOWN,
                reasons=reasons,
                category_code=source_text,
                category_label=source_text,
            )

        if age <= max_age:
            reasons.append(REASON_MATCH)
            return EligibilityResult(
                status=STATUS_COMPATIBLE,
                reasons=reasons,
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
            # Task 9: a classe do jogador foi removida — não é mais critério de
            # compatibilidade. Categorias por classe passam a casar apenas por
            # gênero (verificado em evaluate_player_category) e idade quando houver.
            return STATUS_COMPATIBLE

        if t in (PlayerCategory.TAXONOMY_FPT_AGE, PlayerCategory.TAXONOMY_CBT_AGE,
                 PlayerCategory.TAXONOMY_KIDS):
            return self._check_exact_age(cat, reasons)

        if t == PlayerCategory.TAXONOMY_SENIORS:
            return self._check_seniors(cat, reasons)

        if t == PlayerCategory.TAXONOMY_OPEN:
            return STATUS_COMPATIBLE

        reasons.append(REASON_NO_RULE)
        return STATUS_UNKNOWN

    def _check_exact_age(self, cat: PlayerCategory, reasons: list) -> str:
        # Base age rule: player must be <= max_age (e.g. "14 anos" = up to 14 years old).
        # This is a PRE-CHECK only. _apply_tournament_youth_policy() always runs after and
        # restricts to official_age in default mode, or per-circuit limits in advanced mode.
        # min_age on age categories is metadata only — does not restrict entry downward.
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

    def _get_circuit_hint(self, edition: TournamentEdition) -> Optional[str]:
        """
        Return an informational hint when the tournament requires a federation ranking
        that the profile does not have. Never blocks eligibility — only informational.
        """
        circuit = (edition.tournament.circuit or '').upper()
        ext = getattr(self.profile, 'external_ids', None) or {}
        if 'COSAT' in circuit and not ext.get('cosat_id'):
            return REASON_COSAT_RANKING_REQUIRED
        modality = (edition.tournament.modality or '').lower()
        title_lower = edition.title.lower()
        if 'itf' in circuit or ('itf' in title_lower and 'junior' in title_lower):
            if not ext.get('itf_id'):
                return REASON_ITF_RANKING_REQUIRED
        return None

    def evaluate_edition(self, edition: TournamentEdition) -> dict:
        results = []
        compatible_count = 0
        incompatible_count = 0
        unknown_count = 0
        not_normalized_count = 0
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
                if REASON_NOT_NORMALIZED in r.reasons:
                    not_normalized_count += 1

        circuit_hint = self._get_circuit_hint(edition)
        return {
            'edition_id': edition.id,
            'profile_id': self.profile.id,
            'sporting_age': self.sporting_age,
            'total_count': len(results),
            'compatible_count': compatible_count,
            'incompatible_count': incompatible_count,
            'unknown_count': unknown_count,
            'not_normalized_count': not_normalized_count,
            'circuit_hint': circuit_hint,
            'categories': results,
        }
