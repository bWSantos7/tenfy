"""Normalização de texto para nomes de torneios (TASK 4).

O conserto principal é na origem (extractor passou a ler as páginas do Tênis
Integrado como UTF-8, não latin-1). Aqui ficam utilitários defensivos para que
o Tenfy nunca exiba/persista nomes quebrados, mesmo que algum dado antigo ou de
outra fonte chegue com mojibake.
"""
from __future__ import annotations


def demojibake(text: str) -> str:
    """Conserta texto UTF-8 que foi decodificado como latin-1.

    Ex.: 'TÃªnis' -> 'Tênis', '8Âª Etapa' -> '8ª Etapa', 'PoÃ§os' -> 'Poços'.

    Seguro: só altera quando o round-trip latin-1->utf-8 é válido **e** reduz os
    marcadores de mojibake (Ã/Â). Nomes corretos como 'São Paulo' são preservados
    (o round-trip falha e retornamos o original).
    """
    if not text or ('Ã' not in text and 'Â' not in text):
        return text
    try:
        fixed = text.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    if fixed == text:
        return text
    markers = text.count('Ã') + text.count('Â')
    if fixed.count('Ã') + fixed.count('Â') < markers:
        return fixed
    return text