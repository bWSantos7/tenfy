"""
Management command: audit_data_quality
Audits TournamentEdition records for common data quality issues.
Run: python manage.py audit_data_quality [--fix] [--dry-run]
"""
import re
from django.core.management.base import BaseCommand
from django.db.models import Q

VALID_UF = {
    'AC','AL','AM','AP','BA','CE','DF','ES','GO','MA',
    'MG','MS','MT','PA','PB','PE','PI','PR','RJ','RN',
    'RO','RR','RS','SC','SE','SP','TO',
}

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
BEACH_TENNIS_RE = re.compile(r'beach[\s_-]?tennis|beachtennis', re.IGNORECASE)
PADEL_RE = re.compile(r'padel', re.IGNORECASE)


class Command(BaseCommand):
    help = 'Audit tournament data quality and optionally apply safe auto-fixes'

    def add_arguments(self, parser):
        parser.add_argument('--fix', action='store_true', help='Apply safe automatic fixes')
        parser.add_argument('--limit', type=int, default=0, help='Limit editions checked (0=all)')

    def handle(self, *args, **options):
        from apps.tournaments.models import TournamentEdition

        fix = options['fix']
        limit = options['limit']

        qs = TournamentEdition.objects.select_related(
            'tournament', 'tournament__organization', 'venue'
        ).order_by('id')
        if limit:
            qs = qs[:limit]

        total = qs.count()
        self.stdout.write(f'\nAuditando {total} TournamentEditions...\n')

        issues = {
            'missing_state': [],
            'invalid_state': [],
            'missing_modality': [],
            'beach_in_tennis': [],
            'tennis_in_beach': [],
            'email_in_city': [],
            'is_youth_none': [],
            'cosat_not_youth': [],
        }

        fixed = 0

        for ed in qs:
            venue = ed.venue
            state = venue.state if venue else None
            city = venue.city if venue else None
            modality = ed.tournament.modality if ed.tournament else None
            title = ed.title or ''
            org_name = (ed.tournament.organization.name if ed.tournament and ed.tournament.organization else '') or ''

            # Missing state
            if not state:
                issues['missing_state'].append(ed.id)

            # Invalid state
            elif state.upper() not in VALID_UF:
                issues['invalid_state'].append((ed.id, state))

            # Email in city
            if city and EMAIL_RE.search(city):
                issues['email_in_city'].append((ed.id, city))

            # Missing modality
            if not modality:
                issues['missing_modality'].append(ed.id)
                if fix:
                    combined = f"{title} {org_name}"
                    if BEACH_TENNIS_RE.search(combined):
                        inferred = 'beach_tennis'
                    elif PADEL_RE.search(combined):
                        inferred = 'padel'
                    else:
                        inferred = 'tennis'
                    ed.tournament.modality = inferred
                    ed.tournament.save(update_fields=['modality'])
                    fixed += 1
                    self.stdout.write(f'  [FIX] Edition {ed.id}: modality set to {inferred}')

            # Beach tennis tournament in tennis context (or vice versa)
            if modality == 'tennis' and BEACH_TENNIS_RE.search(title + ' ' + org_name):
                issues['beach_in_tennis'].append((ed.id, title))
                if fix:
                    ed.tournament.modality = 'beach_tennis'
                    ed.tournament.save(update_fields=['modality'])
                    fixed += 1
                    self.stdout.write(f'  [FIX] Edition {ed.id}: corrected tennis→beach_tennis: {title[:60]}')

            if modality == 'beach_tennis' and not BEACH_TENNIS_RE.search(title + ' ' + org_name):
                if 'tenis' in (title + ' ' + org_name).lower() or 'tênis' in (title + ' ' + org_name).lower():
                    issues['tennis_in_beach'].append((ed.id, title))

            # is_youth not set (None = unclassified)
            if ed.is_youth is None:
                issues['is_youth_none'].append(ed.id)

            # COSAT/ITF tournaments not marked as youth
            source_name = (ed.source_name or '').lower()
            if 'cosat' in source_name or 'cosant' in source_name or 'itf' in source_name:
                if ed.is_youth is False:
                    issues['cosat_not_youth'].append(ed.id)

        # Report
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write('RELATÓRIO DE AUDITORIA DE DADOS')
        self.stdout.write('=' * 60)
        self.stdout.write(f'Total analisado: {total}')
        self.stdout.write(f'Sem estado/UF:            {len(issues["missing_state"])} edições')
        self.stdout.write(f'UF inválida:              {len(issues["invalid_state"])} edições')
        self.stdout.write(f'Sem modalidade:           {len(issues["missing_modality"])} edições')
        self.stdout.write(f'Beach Tennis como Tênis:  {len(issues["beach_in_tennis"])} edições')
        self.stdout.write(f'Tênis como Beach Tennis:  {len(issues["tennis_in_beach"])} edições')
        self.stdout.write(f'Email no campo cidade:    {len(issues["email_in_city"])} edições')
        self.stdout.write(f'is_youth não classificado:{len(issues["is_youth_none"])} edições')
        self.stdout.write(f'COSAT/ITF não juvenil:    {len(issues["cosat_not_youth"])} edições')

        if issues['invalid_state']:
            self.stdout.write('\nUFs inválidas encontradas:')
            for eid, uf in issues['invalid_state'][:20]:
                self.stdout.write(f'  Edition {eid}: "{uf}"')

        if issues['beach_in_tennis']:
            self.stdout.write('\nBeach Tennis classificado como Tênis:')
            for eid, title in issues['beach_in_tennis'][:20]:
                self.stdout.write(f'  Edition {eid}: {title[:70]}')

        if issues['email_in_city']:
            self.stdout.write('\nEmail no campo cidade:')
            for eid, city in issues['email_in_city'][:10]:
                self.stdout.write(f'  Edition {eid}: {city[:60]}')

        if fix:
            self.stdout.write(f'\nCorreções aplicadas: {fixed}')
        else:
            self.stdout.write('\nPara aplicar correções seguras automáticas, use: --fix')
            self.stdout.write('Correções manuais (UF inválida, email em cidade) devem ser feitas via admin.')

        self.stdout.write('\nComando para rodar em produção:')
        self.stdout.write('  railway run python manage.py audit_data_quality')
        self.stdout.write('  railway run python manage.py audit_data_quality --fix')
