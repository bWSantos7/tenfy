"""
Backfill: aplica a regra de matching corrigida a TODOS os perfis existentes.

Corrige dados já gravados antes do fix (PR #50):
  A) Inscrições ATIVAS cujo FederationEntry correspondente está removed_or_replaced
     (atleta cancelou/foi removido) → marca como cancelada (vai p/ Histórico).
  B) Cria inscrições que faltam (passadas e futuras) via match_profile_now, que já
     respeita removed_or_replaced e não ressuscita canceladas.

Uso:
    python manage.py backfill_profile_matches            # dry-run (padrão)
    python manage.py backfill_profile_matches --no-dry-run
"""
from difflib import SequenceMatcher

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.players.models import PlayerProfile
from apps.registrations.models import FederationEntry, TournamentRegistration
from apps.registrations.tasks import match_profile_now, _normalize


def _matching_entries(edition_id, profile):
    """FederationEntries da edição que correspondem ao perfil (external_id ou nome)."""
    ext_ids = profile.external_ids or {}
    pn = _normalize(profile.display_name or '')
    matches = []
    for e in FederationEntry.objects.filter(edition_id=edition_id):
        if e.player_external_id and str(ext_ids.get(e.source, '')) == e.player_external_id:
            matches.append(e)
            continue
        if pn and e.player_name and SequenceMatcher(None, _normalize(e.player_name), pn).ratio() > 0.95:
            matches.append(e)
    return matches


class Command(BaseCommand):
    help = 'Backfill do matching corrigido em todos os perfis (Card/fix tasks2).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', default=True)
        parser.add_argument('--no-dry-run', dest='dry_run', action='store_false')

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        self.stdout.write(self.style.SUCCESS(f'=== backfill_profile_matches dry_run={dry} ==='))
        stats = {'profiles': 0, 'created': 0, 'corrected_withdrawn': 0}

        profiles = PlayerProfile.objects.all()
        for profile in profiles:
            stats['profiles'] += 1

            # B) Cria inscrições faltantes (passadas/futuras), respeitando removed.
            if not dry:
                try:
                    res = match_profile_now(profile.id)
                    stats['created'] += res.get('registrations_created', 0)
                except Exception as exc:  # noqa: BLE001
                    self.stdout.write(self.style.ERROR(f'  match profile {profile.id} falhou: {exc}'))

            # A) Corrige inscrições ATIVAS cujo entry está removido/substituído.
            active = TournamentRegistration.objects.filter(
                profile=profile, is_withdrawn=False,
            ).select_related('edition')
            for reg in active:
                entries = _matching_entries(reg.edition_id, profile)
                if entries and all(e.removed_or_replaced for e in entries):
                    self.stdout.write(
                        f'  corrigir: profile {profile.id} ed {reg.edition_id} '
                        f'"{(reg.edition.title or "")[:30]}" → cancelada (entry removida)'
                    )
                    stats['corrected_withdrawn'] += 1
                    if not dry:
                        reg.is_withdrawn = True
                        reg.withdrawn_at = timezone.now()
                        reg.save(update_fields=['is_withdrawn', 'withdrawn_at', 'updated_at'])
                        # espelha na agenda
                        from apps.watchlist.models import WatchlistItem
                        WatchlistItem.objects.filter(
                            user_id=profile.user_id, edition_id=reg.edition_id,
                        ).update(user_status='withdrawn')

        self.stdout.write('\n=== Resultado ===')
        for k, v in stats.items():
            self.stdout.write(f'  {k}: {v}')
        if dry:
            self.stdout.write(self.style.WARNING('\nDRY-RUN — nada alterado. Use --no-dry-run para aplicar.'))
        else:
            self.stdout.write(self.style.SUCCESS('\nConcluído.'))
