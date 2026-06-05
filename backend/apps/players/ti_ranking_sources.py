"""
Configurable registry mapping a data *source* (cbt / fpt / fct / …) to the
Tênis Integrado ranking ids it exposes.

Why a registry instead of crawling everything?
  * CBT national rankings are public and stable under /new_ranking/index_ranking/2.
  * Federation-scoped rankings (FPT/SP, FCT, …) are localised by the logged-in
    user on TI, so their ranking_ids cannot be discovered reliably without
    authentication. We therefore configure the known ids here and let the admin
    extend the registry as new ones are confirmed (e.g. via the --discover mode
    of sync_ti_rankings).

Each entry:
  ranking_external_id → the TI ranking id used in
                        /ranking_painel_classif/index/{id}
  ranking_name        → human label (preserved on each imported row)
  federation          → friendly federation/entity name
  modality            → optional modality hint (tennis / beach_tennis / …)

This data is curated/operational, never invented: ids below were confirmed
against the public TI site. Empty source lists are valid and simply mean
"awaiting confirmed ranking ids".
"""
from __future__ import annotations

# Discovered against the public TI site (CBT confederation rankings).
# Beach-tennis / padel rankings are intentionally excluded from the default
# tennis import but kept here documented for future expansion.
TI_RANKING_SOURCES: dict[str, dict] = {
    'cbt': {
        'federation': 'Confederação Brasileira de Tênis',
        # Scope (confirmed with contratante): only the national Juvenil ranking.
        # Ranking 1326 exposes exactly the 8 youth categories the product needs —
        # 12/14/16/18 anos Masculino Simples and 12/14/16/18 anos Feminino Simples.
        # Other CBT rankings (Interclubes, Profissionais, Masters, Beach Tennis…)
        # exist under /new_ranking/index_ranking/2 but are intentionally out of
        # scope for now; add them here when requested.
        'rankings': [
            {'ranking_external_id': '1326', 'ranking_name': 'Ranking Nacional Juvenil', 'modality': 'tennis'},
        ],
    },
    # FPT/SP and FCT rankings are localised by login on TI. Confirmed ranking_ids
    # should be appended here (use `manage.py sync_ti_rankings --discover` to list
    # candidates). Kept empty rather than guessed to avoid importing wrong data.
    'fpt': {
        'federation': 'Federação Paulista de Tênis',
        'rankings': [],
    },
    'fct': {
        'federation': 'Federação Catarinense de Tênis',
        'rankings': [],
    },
}


def get_source_rankings(source: str) -> list[dict]:
    """Return the configured ranking descriptors for a source (empty if unknown)."""
    return TI_RANKING_SOURCES.get(source, {}).get('rankings', [])


def get_source_federation(source: str) -> str:
    return TI_RANKING_SOURCES.get(source, {}).get('federation', '')


def all_sources() -> list[str]:
    return list(TI_RANKING_SOURCES.keys())
