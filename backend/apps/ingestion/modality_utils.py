"""
Shared modality inference for tournament connectors.

Supported modalities (matches Tournament.modality choices):
  tennis, beach_tennis, padel, wheelchair
"""
import re


# Keywords that signal each modality (checked in title, circuit, route, department).
_BEACH_TENNIS_KW = frozenset({
    'beach', 'praia', 'beachtennis', 'beach tennis', 'bt ', ' bt',
})
_WHEELCHAIR_KW = frozenset({
    'wheelchair', 'cadeira de rodas', 'cadeira', 'adaptado', 'paralímpico',
    'paralimpico',
})
_PADEL_KW = frozenset({'padel', 'pádel'})

# Match a full "beach tennis" substring or standalone "bt" token
_BEACH_RE = re.compile(r'\b(beach\s*tennis|bt)\b', re.IGNORECASE)
_BEACH_TENNIS_PHRASE_RE = re.compile(r'beach\s*tennis', re.IGNORECASE)
_WHEELCHAIR_RE = re.compile(
    r'\b(wheelchair|cadeira\s*de\s*rodas|adaptado|paralímpico|paralimpico)\b',
    re.IGNORECASE,
)
_PADEL_RE = re.compile(r'\bpadel\b', re.IGNORECASE)
# Explicit "tênis" / "tenis" in the title signals the event IS tennis — used to
# prevent venue names like "Praia Clube" or "Praia Brava" from triggering false
# beach_tennis reclassification.
_EXPLICIT_TENNIS_RE = re.compile(r'\bt[eê]nis\b', re.IGNORECASE)


def infer_modality(*text_fields: str) -> str:
    """
    Infer tournament modality from one or more text fields (title, circuit,
    route, department name, venue name, etc.).

    The FIRST two fields (title + circuit) are treated as PRIMARY signals.
    Additional fields (e.g. venue name) are SECONDARY: a venue containing only
    "praia" or "beach" (without "beach tennis" as a phrase) will NOT override a
    title that explicitly says "tênis".

    Returns one of: tennis | beach_tennis | padel | wheelchair.
    Falls back to 'tennis' when nothing matches.

    Examples:
        >>> infer_modality('Copa Beach Tennis SP 2026', 'FPT')
        'beach_tennis'
        >>> infer_modality('FCT 100 - ARENA GUTO', 'FCT', 'Arena Guto Beach Tennis')
        'beach_tennis'
        >>> infer_modality('Campeonato Brasileiro de Tênis', 'CBT', 'Praia Clube')
        'tennis'
        >>> infer_modality('Torneio de Padel', '')
        'padel'
    """
    fields = [f.strip() for f in text_fields if f and isinstance(f, str)]
    if not fields:
        return 'tennis'

    # Primary signal: title + circuit (first two fields)
    primary = ' '.join(fields[:2]).lower()
    # Full combined text including venue names
    combined = ' '.join(fields).lower()

    # If title/circuit contains "beach tennis" explicitly → beach_tennis
    if _BEACH_RE.search(primary) or 'beach' in primary or 'praia' in primary:
        return 'beach_tennis'

    # If title/circuit contains plain "tênis" (without beach) → tennis wins even
    # if a venue name has "praia" or "beach" in it (prevents "Praia Clube" false positives)
    if _EXPLICIT_TENNIS_RE.search(primary) and 'beach' not in primary:
        return 'tennis'

    if _PADEL_RE.search(primary):
        return 'padel'

    if _WHEELCHAIR_RE.search(primary) or 'cadeira' in primary:
        return 'wheelchair'

    # Secondary signal: venue names — only upgrade to beach_tennis when the venue
    # contains the full phrase "beach tennis" (not just "beach" or "praia" alone)
    if _BEACH_TENNIS_PHRASE_RE.search(combined):
        return 'beach_tennis'

    # Loose secondary: "beach" or "praia" anywhere in venue — only apply when
    # there is NO explicit tennis signal in primary fields
    if 'beach' in combined or 'praia' in combined:
        return 'beach_tennis'

    if _PADEL_RE.search(combined):
        return 'padel'

    if _WHEELCHAIR_RE.search(combined) or 'cadeira' in combined:
        return 'wheelchair'

    return 'tennis'
