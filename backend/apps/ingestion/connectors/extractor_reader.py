"""
Leitor do schema ``extractor`` (tournament-extractor) no mesmo PostgreSQL.

O serviço externo *tournament-extractor* (repositório separado, roda no Railway)
popula um schema dedicado ``extractor`` no MESMO banco do Tenfy, com as tabelas:

    extractor.sources, extractor.tournaments, extractor.tournament_categories,
    extractor.entrants, extractor.extraction_runs, extractor.extraction_errors

Este módulo apenas LÊ essas tabelas (nunca escreve) e devolve dicionários
prontos para o ``sync_from_extractor`` mapear para TournamentEdition/FederationEntry.

Substitui os antigos conectores in-backend e os syncs Mongo/n8n.
"""
from __future__ import annotations

import logging
from typing import Iterator, Optional

from django.conf import settings
from django.db import connection

logger = logging.getLogger('apps.ingestion.extractor')

# Schema configurável; o extractor usa "extractor" por padrão.
SCHEMA = getattr(settings, 'EXTRACTOR_DB_SCHEMA', 'extractor')


def _q(table: str) -> str:
    """Nome de tabela schema-qualificado e citado."""
    return f'"{SCHEMA}"."{table}"'


def is_available() -> bool:
    """True se o schema do extractor e a tabela de torneios existem."""
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = %s AND table_name = 'tournaments'
            )
            """,
            [SCHEMA],
        )
        row = cur.fetchone()
        return bool(row and row[0])


def _rows(cur) -> list[dict]:
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def iter_tournaments(
    source: Optional[str] = None,
    limit: Optional[int] = None,
    only_youth: bool = True,
) -> Iterator[dict]:
    """Itera torneios do extractor já com categorias e inscritos aninhados.

    Cada item: { ...campos do torneio..., 'source_name', 'categories': [...],
    'entrants': [...] }.
    """
    where = []
    params: list = []
    if only_youth:
        where.append('t.is_youth = TRUE')
    if source:
        where.append('s.name = %s')
        params.append(source)
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''
    limit_sql = f'LIMIT {int(limit)}' if limit else ''

    with connection.cursor() as cur:
        cur.execute(
            f"""
            SELECT t.*, s.name AS source_name, s.base_url AS source_base_url,
                   s.type AS source_type
            FROM {_q('tournaments')} t
            JOIN {_q('sources')} s ON s.id = t.source_id
            {where_sql}
            ORDER BY t.start_date NULLS LAST, t.id
            {limit_sql}
            """,
            params,
        )
        tournaments = _rows(cur)

    for t in tournaments:
        t['categories'] = _categories_for(t['id'])
        t['entrants'] = _entrants_for(t['id'])
        yield t


def _categories_for(tournament_id: int) -> list[dict]:
    with connection.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, name, normalized_name, age_group, gender, category_type
            FROM {_q('tournament_categories')}
            WHERE tournament_id = %s
            ORDER BY age_group NULLS LAST, name
            """,
            [tournament_id],
        )
        return _rows(cur)


def _entrants_for(tournament_id: int) -> list[dict]:
    with connection.cursor() as cur:
        cur.execute(
            f"""
            SELECT e.id, e.category_id, e.external_id, e.name, e.country, e.state,
                   e.city, e.ranking, e.position, e.rating, e.payment_status,
                   e.registration_status, e.raw_data, c.name AS category_name
            FROM {_q('entrants')} e
            LEFT JOIN {_q('tournament_categories')} c ON c.id = e.category_id
            WHERE e.tournament_id = %s
            ORDER BY c.name NULLS LAST, e.position NULLS LAST, e.name
            """,
            [tournament_id],
        )
        return _rows(cur)


def source_counts() -> list[dict]:
    """Resumo por fonte (para o painel/admin): torneios e inscritos."""
    with connection.cursor() as cur:
        cur.execute(
            f"""
            SELECT s.name AS source,
                   COUNT(DISTINCT t.id) AS tournaments,
                   COUNT(e.id) AS entrants
            FROM {_q('sources')} s
            LEFT JOIN {_q('tournaments')} t ON t.source_id = s.id
            LEFT JOIN {_q('entrants')} e ON e.tournament_id = t.id
            GROUP BY s.name
            ORDER BY s.name
            """
        )
        return _rows(cur)
