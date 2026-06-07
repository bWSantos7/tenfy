"""
Card 3 (tasks2) — consolida torneios/edições duplicados em PostgreSQL.

Duplicados surgem quando o mesmo evento foi importado sob Tournaments
(canonical_slug) diferentes — p.ex. o mesmo registro do Tênis Integrado importado
por conectores diferentes (cbt_public vs cbt_youth), ou o mesmo id TI sob prefixos
de federação diferentes (cbt:23120 vs fct:23120).

Estratégia CONSERVADORA (só funde quando é seguramente o mesmo evento):
  1. external_id idêntico + mesma temporada  (ex.: "cbt:22777" repetido).
  2. id TI normalizado + mesma temporada      (ex.: "cbt:23120" e "fct:23120").

NÃO funde por "cidade+data" com títulos diferentes (poderiam ser eventos
distintos no mesmo clube/dia — masculino x feminino, etc.).

Para cada grupo, escolhe o "sobrevivente" mais completo, repõe as relações
(inscritos, watchlist, inscrições, alertas, etc.) para ele, preenche campos
vazios do sobrevivente com dados do duplicado e remove o duplicado. Tournaments
que ficarem sem edições são removidos.

Uso:
    python manage.py dedupe_tournament_editions                 # dry-run (padrão)
    python manage.py dedupe_tournament_editions --no-dry-run     # aplica
"""
import re
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction, IntegrityError

from apps.tournaments.models import (
    Tournament, TournamentEdition, TournamentCategory,
)

# Prefixos de federações que vêm do Tênis Integrado e compartilham o mesmo id TI.
_TI_PREFIX_RE = re.compile(r'^(?:cbt|fct|fpt-sp|fpt|fbt)\s*:\s*(\d+)$', re.IGNORECASE)


def _ti_key(external_id: str):
    m = _TI_PREFIX_RE.match((external_id or '').strip())
    return m.group(1) if m else None


def _score(ed) -> tuple:
    """Maior = mais completo. Empate → menor id (mais antigo) vence."""
    from apps.registrations.models import FederationEntry
    return (
        1 if ed.is_published else 0,
        FederationEntry.objects.filter(edition=ed).count(),
        ed.categories.count(),
        1 if ed.venue_id else 0,
        len(ed.acceptance_list or []),
        -ed.id,
    )


class Command(BaseCommand):
    help = 'Consolida edições de torneios duplicadas (Card 3 tasks2).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', default=True,
                            help='Apenas mostra o que faria (padrão).')
        parser.add_argument('--no-dry-run', dest='dry_run', action='store_false',
                            help='Aplica o merge no banco.')

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        self.stdout.write(self.style.SUCCESS(f'=== dedupe_tournament_editions dry_run={dry} ==='))

        stats = {'groups': 0, 'merged': 0, 'relations_moved': 0, 'relations_dropped': 0,
                 'tournaments_removed': 0}
        # Tournaments cujas edições duplicadas foram removidas neste run — só esses
        # são candidatos a remoção se ficarem órfãos (não mexemos em órfãos pré-existentes).
        self._affected_tournaments: set[int] = set()

        # ── Passo 1: external_id (case-insensitive) ──────────────────────────
        self._dedupe_by_key(
            lambda e: (e.season_year, e.external_id.lower()) if e.external_id else None,
            'external_id', dry, stats,
        )
        # ── Passo 2: id TI normalizado (prefixos de federação) ───────────────
        self._dedupe_by_key(
            lambda e: (e.season_year, 'ti:' + _ti_key(e.external_id)) if _ti_key(e.external_id) else None,
            'ti_id', dry, stats,
        )

        # ── Limpa apenas Tournaments que ficaram órfãos POR ESTE merge ───────
        # (não tocamos em órfãos pré-existentes, fora do escopo da deduplicação).
        if dry:
            # Em dry-run, estima quantos dos tournaments dos duplicados ficariam órfãos.
            stats['tournaments_removed'] = Tournament.objects.filter(
                id__in=self._affected_tournaments, editions__isnull=True,
            ).count()
        else:
            orphans = Tournament.objects.filter(
                id__in=self._affected_tournaments, editions__isnull=True,
            )
            stats['tournaments_removed'] = orphans.count()
            orphans.delete()

        self.stdout.write('\n=== Resultado ===')
        for k, v in stats.items():
            self.stdout.write(f'  {k}: {v}')
        if dry:
            self.stdout.write(self.style.WARNING('\nDRY-RUN — nada foi alterado. Use --no-dry-run para aplicar.'))
        else:
            self.stdout.write(self.style.SUCCESS('\nConcluído.'))

    def _dedupe_by_key(self, keyfn, label, dry, stats):
        groups = defaultdict(list)
        for ed in TournamentEdition.objects.select_related('tournament', 'venue').all():
            k = keyfn(ed)
            if k:
                groups[k].append(ed)

        for key, eds in groups.items():
            if len(eds) < 2:
                continue
            stats['groups'] += 1
            survivor = max(eds, key=_score)
            dups = [e for e in eds if e.id != survivor.id]
            self.stdout.write(
                f'  [{label}] {key} → mantém edition {survivor.id} '
                f'("{survivor.title[:40]}"), funde {[d.id for d in dups]}'
            )
            if dry:
                continue
            for dup in dups:
                self._affected_tournaments.add(dup.tournament_id)
                self._merge_into(dup, survivor, stats)
                stats['merged'] += 1

    @transaction.atomic
    def _merge_into(self, dup, survivor, stats):
        # 1) Repointar todas as relações que apontam para a edição duplicada.
        for rel in TournamentEdition._meta.related_objects:
            model = rel.related_model
            fk_id = rel.field.attname  # ex.: 'edition_id' / 'tournament_edition_id'
            # TournamentCategory não tem unique → tratar para não duplicar categorias.
            if model is TournamentCategory:
                existing = set(
                    survivor.categories.values_list('source_category_text', flat=True)
                )
                for cat in model.objects.filter(**{fk_id: dup.id}):
                    if cat.source_category_text in existing:
                        cat.delete()
                        stats['relations_dropped'] += 1
                    else:
                        setattr(cat, fk_id, survivor.id)
                        cat.save(update_fields=[fk_id])
                        stats['relations_moved'] += 1
                continue
            for obj in model.objects.filter(**{fk_id: dup.id}):
                setattr(obj, fk_id, survivor.id)
                try:
                    with transaction.atomic():
                        obj.save(update_fields=[fk_id])
                    stats['relations_moved'] += 1
                except IntegrityError:
                    # Sobrevivente já tem registro equivalente (unique) → descarta o do dup.
                    obj.delete()
                    stats['relations_dropped'] += 1

        # 2) Backfill de campos vazios do sobrevivente com dados do duplicado.
        updates = {}
        if not survivor.venue_id and dup.venue_id:
            updates['venue_id'] = dup.venue_id
        for f in ('start_date', 'end_date', 'entry_open_at', 'entry_close_at',
                  'official_source_url', 'base_price_brl'):
            if not getattr(survivor, f) and getattr(dup, f):
                updates[f] = getattr(dup, f)
        if not (survivor.acceptance_list or []) and (dup.acceptance_list or []):
            updates['acceptance_list'] = dup.acceptance_list
        if not survivor.is_published and dup.is_published:
            updates['is_published'] = True
        if updates:
            for k, v in updates.items():
                setattr(survivor, k, v)
            survivor.save(update_fields=list(updates.keys()) + ['updated_at'])

        # 3) Remover a edição duplicada.
        dup.delete()
