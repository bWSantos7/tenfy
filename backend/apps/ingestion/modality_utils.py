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
_WHEELCHAIR_RE = re.compile(
    r'\b(wheelchair|cadeira\s*de\s*rodas|adaptado|paralímpico|paralimpico)\b',
    re.IGNORECASE,
)
_PADEL_RE = re.compile(r'\bpadel\b', re.IGNORECASE)


def infer_modality(*text_fields: str) -> str:
    """
    Infer tournament modality from one or more text fields (title, circuit,
    route, department name, etc.).  Returns one of: tennis | beach_tennis |
    padel | wheelchair.  Falls back to 'tennis' when nothing matches.

    Args:
        *text_fields: Any number of string fields to inspect.  None values
                      and empty strings are silently skipped.

    Examples:
        >>> infer_modality('Copa Beach Tennis SP 2026', 'FPT')
        'beach_tennis'
        >>> infer_modality('Open Masculino', 'Interclubes SP')
        'tennis'
        >>> infer_modality('Torneio de Padel', '')
        'padel'
    """
    combined = ' '.join(f.strip() for f in text_fields if f and isinstance(f, str)).lower()

    if not combined:
        return 'tennis'

    if _BEACH_RE.search(combined) or 'beach' in combined or 'praia' in combined:
        return 'beach_tennis'

    if _PADEL_RE.search(combined):
        return 'padel'

    if _WHEELCHAIR_RE.search(combined) or 'cadeira' in combined:
        return 'wheelchair'

    return 'tennis'
