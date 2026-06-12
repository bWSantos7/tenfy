"""
Matching flexível entre inscritos de fontes externas (COSAT / ITF / UTR) e os
perfis esportivos da Tenfy.

Nas fontes externas o nome do atleta costuma vir abreviado ou em ordem
diferente (ex.: COSAT "Julia Nardy" para o perfil "Julia Alves Nardy"), então o
match por nome exato não basta. Este módulo implementa uma comparação por tokens
(primeiro nome, último sobrenome, sobrenomes intermediários, abreviações,
normalização de acento/caixa) e devolve um nível de confiança.

IMPORTANTE: este caminho é usado SOMENTE para as fontes COSAT/ITF/UTR. As fontes
de Tênis Integrado (CBT/FPT/FCT) já têm match por ID externo e seguem o caminho
antigo, intocado.

Decisões de segurança (evitar falso positivo):
  - Só auto-inscreve em confiança ALTA, ou MÉDIA quando há corroboração
    (gênero da categoria == gênero do perfil e idade plausível).
  - Gênero incompatível entre categoria e perfil bloqueia o match.
  - Idade muito acima do teto da categoria (Uxx) bloqueia o auto-match.
  - Confiança baixa vira "possível correspondência" para auditoria, sem inscrever.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List, Optional

# Fontes cobertas por este matching flexível.
FLEX_SOURCES = {'cosat', 'itf', 'utr'}

CONF_HIGH = 'high'
CONF_MEDIUM = 'medium'
CONF_LOW = 'low'
CONF_NONE = 'none'


def normalize_name(text: str) -> str:
    """Minúsculas, sem acento, sem pontuação, espaços colapsados."""
    if not text:
        return ''
    n = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    n = re.sub(r'[^a-z0-9\s]', ' ', n.lower())
    return re.sub(r'\s+', ' ', n).strip()


# Partículas de sobrenome que não distinguem pessoas (ignoradas na tokenização).
_PARTICLES = {'de', 'da', 'do', 'dos', 'das', 'e', 'del', 'la', 'van', 'von', 'di'}


def name_tokens(text: str) -> List[str]:
    """Tokens significativos do nome (sem partículas tipo 'de'/'da')."""
    toks = [t for t in normalize_name(text).split() if t not in _PARTICLES]
    return toks


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _tok_eq(a: str, b: str) -> bool:
    """Igualdade de token tolerante: igual, inicial (ex.: 'j' ~ 'julia') ou
    altamente similar (typo/variação já normalizada)."""
    if a == b:
        return True
    if len(a) == 1 and b.startswith(a):
        return True
    if len(b) == 1 and a.startswith(b):
        return True
    if len(a) >= 3 and len(b) >= 3 and _sim(a, b) >= 0.9:
        return True
    return False


def _is_subset(small: List[str], big: List[str]) -> bool:
    """True se todo token de `small` casa com um token distinto de `big`
    (um é abreviação do outro, ex.: {julia,nardy} ⊆ {julia,alves,nardy})."""
    if not small:
        return False
    used = [False] * len(big)
    for t in small:
        hit = False
        for i, u in enumerate(big):
            if not used[i] and _tok_eq(t, u):
                used[i] = True
                hit = True
                break
        if not hit:
            return False
    return True


@dataclass
class NameMatch:
    confidence: str   # high | medium | low | none
    score: float
    reason: str


def match_names(entry_name: str, profile_name: str) -> NameMatch:
    """Compara dois nomes e devolve confiança + motivo (sem decidir inscrição)."""
    e = name_tokens(entry_name)
    p = name_tokens(profile_name)
    if not e or not p:
        return NameMatch(CONF_NONE, 0.0, 'nome vazio')

    ne, np = ' '.join(e), ' '.join(p)
    if ne == np:
        return NameMatch(CONF_HIGH, 1.0, 'nome idêntico (normalizado)')

    full_ratio = _sim(ne, np)
    first_eq = _tok_eq(e[0], p[0])
    last_eq = _tok_eq(e[-1], p[-1])
    subset = _is_subset(e, p) or _is_subset(p, e)

    if first_eq and last_eq:
        if subset:
            # Um nome é abreviação do outro (caso Julia Nardy / Julia Alves Nardy).
            return NameMatch(CONF_HIGH, max(full_ratio, 0.95),
                             'primeiro nome + último sobrenome iguais; um é abreviação do outro')
        return NameMatch(CONF_MEDIUM, max(full_ratio, 0.85),
                         'primeiro nome + último sobrenome iguais; nomes do meio diferentes')

    if first_eq and not last_eq:
        return NameMatch(CONF_LOW, full_ratio, 'mesmo primeiro nome, último sobrenome diferente')
    if last_eq and not first_eq:
        return NameMatch(CONF_LOW, full_ratio, 'mesmo último sobrenome, primeiro nome diferente')

    # Sem âncora de primeiro/último: cai na similaridade global da string inteira.
    if full_ratio >= 0.95:
        return NameMatch(CONF_HIGH, full_ratio, 'similaridade global muito alta')
    if full_ratio >= 0.86:
        return NameMatch(CONF_MEDIUM, full_ratio, 'similaridade global alta')
    if full_ratio >= 0.75:
        return NameMatch(CONF_LOW, full_ratio, 'similaridade global moderada')
    return NameMatch(CONF_NONE, full_ratio, 'sem correspondência')


# ── Sinais da categoria (gênero/idade) para corroborar e evitar falso positivo ──

def category_gender(category_text: str) -> Optional[str]:
    """'M' / 'F' inferido da categoria (COSAT 'Girls/Boys Singles', ITF
    'Feminino/Masculino'); None quando indefinido/misto."""
    t = normalize_name(category_text)
    if not t:
        return None
    if 'mist' in t or 'mixed' in t:
        return None
    if re.search(r'\b(girls?|femin\w*|feminin\w*|wta|ws|gs|gd|wd)\b', t):
        return 'F'
    if re.search(r'\b(boys?|mascul\w*|masculin\w*|atp|ms|bs|bd|md)\b', t):
        return 'M'
    return None


def category_age_cap(category_text: str) -> Optional[int]:
    """Teto de idade da categoria (U16/Sub-16/16 anos → 16). None se não houver."""
    t = normalize_name(category_text)
    m = re.search(r'\b(?:u|sub)\s*-?\s*(\d{1,2})\b', t)
    if m:
        return int(m.group(1))
    m = re.search(r'\b(\d{1,2})\s*(?:anos|years|under)\b', t)
    if m:
        return int(m.group(1))
    return None


@dataclass
class MatchDecision:
    auto_register: bool   # seguro para inscrever automaticamente na Agenda
    possible: bool        # correspondência plausível para auditoria (sem inscrever)
    confidence: str
    score: float
    reason: str


def decide_match(
    *,
    entry_name: str,
    profile_name: str,
    category_text: str = '',
    profile_gender: str = '',
    profile_birth_year: Optional[int] = None,
    tournament_year: Optional[int] = None,
) -> MatchDecision:
    """Combina o match de nome com os safeguards de gênero/idade e decide se é
    seguro inscrever automaticamente. Não acessa o banco — totalmente testável."""
    nm = match_names(entry_name, profile_name)

    # ── Safeguard de gênero (bloqueio forte) ──
    g_cat = category_gender(category_text)
    gender_mismatch = bool(g_cat and profile_gender and g_cat != profile_gender)
    gender_ok = bool(g_cat and profile_gender and g_cat == profile_gender)
    if gender_mismatch:
        return MatchDecision(False, False, CONF_NONE, nm.score,
                             f'{nm.reason} — bloqueado: gênero da categoria ({g_cat}) '
                             f'difere do perfil ({profile_gender})')

    # ── Safeguard de idade (bloqueio quando muito acima do teto da categoria) ──
    cap = category_age_cap(category_text)
    age_block = False
    age_ok = True
    if cap and profile_birth_year and tournament_year:
        age = tournament_year - profile_birth_year
        # Juniores não excedem o teto; tolerância de 2 anos para variações de fonte.
        if age > cap + 2:
            age_block = True
            age_ok = False

    if age_block:
        return MatchDecision(False, False, CONF_NONE, nm.score,
                             f'{nm.reason} — bloqueado: idade incompatível com a categoria (U{cap})')

    if nm.confidence == CONF_HIGH:
        return MatchDecision(True, True, CONF_HIGH, nm.score, nm.reason)

    if nm.confidence == CONF_MEDIUM:
        # Média só auto-inscreve com corroboração (gênero confere e idade plausível).
        if gender_ok and age_ok:
            return MatchDecision(True, True, CONF_MEDIUM, nm.score,
                                 f'{nm.reason} (corroborado por gênero/idade)')
        return MatchDecision(False, True, CONF_MEDIUM, nm.score,
                             f'{nm.reason} (sem corroboração suficiente — registrado como possível)')

    if nm.confidence == CONF_LOW:
        return MatchDecision(False, True, CONF_LOW, nm.score, nm.reason)

    return MatchDecision(False, False, CONF_NONE, nm.score, nm.reason)
