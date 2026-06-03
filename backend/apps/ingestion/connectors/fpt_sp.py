"""
FPT (Federação Paulista de Tênis) connector backed by the Tennis Tool API.

The website fpt.tenisintegrado.com.br is an Angular SPA that calls the same
Tennis Tool API used by CBT. The payload structure is identical — only the
host and system parameters differ.

Departments available (tipo_depto):
  1 – Classes
  2 – Beach Tennis
  3 – Cadeira de rodas
  4 – Juvenil
  5 – Seniors
  7 – Tennis Kids
 12 – Professional
"""
import logging
from datetime import datetime

from .base import BaseConnector, ConnectorError, register_connector
from apps.ingestion.modality_utils import infer_modality

logger = logging.getLogger('apps.ingestion.fpt_sp')


@register_connector
class FPTSPPublicConnector(BaseConnector):
    """All FPT (SP) tournaments via loadAll=1."""

    key = 'fpt_sp_public'

    API_BASE = 'https://api.tennistool.tenisintegrado.com'
    API_PATH = '/tournaments/tournament/getTournamentDepartmentList'
    API_DETAIL_PATH = '/tournaments/tournament/getTournament'
    SYSTEM_ID = '2'
    HOST = 'fpt.tenisintegrado.com.br'

    STATUS_MAP = {
        'inscricoes abertas': 'open',
        'inscrições abertas': 'open',
        'encerrando em breve': 'open',
        'inscricoes encerradas': 'closed',
        'inscrições encerradas': 'closed',
        'torneio iniciado': 'in_progress',
        'em andamento': 'in_progress',
        'chaves publicadas': 'in_progress',
        'torneio encerrado': 'finished',
        'finalizado': 'finished',
        'cancelado': 'canceled',
    }

    STATE_MAP = {
        'acre': 'AC', 'alagoas': 'AL', 'amapa': 'AP', 'amapá': 'AP',
        'amazonas': 'AM', 'bahia': 'BA', 'ceara': 'CE', 'ceará': 'CE',
        'distrito federal': 'DF', 'espirito santo': 'ES', 'espírito santo': 'ES',
        'goias': 'GO', 'goiás': 'GO', 'maranhao': 'MA', 'maranhão': 'MA',
        'mato grosso': 'MT', 'mato grosso do sul': 'MS', 'minas gerais': 'MG',
        'para': 'PA', 'pará': 'PA', 'paraiba': 'PB', 'paraíba': 'PB',
        'parana': 'PR', 'paraná': 'PR', 'pernambuco': 'PE',
        'piaui': 'PI', 'piauí': 'PI', 'rio de janeiro': 'RJ',
        'rio grande do norte': 'RN', 'rio grande do sul': 'RS',
        'rondonia': 'RO', 'rondônia': 'RO', 'roraima': 'RR',
        'santa catarina': 'SC', 'sao paulo': 'SP', 'são paulo': 'SP',
        'sergipe': 'SE', 'tocantins': 'TO',
    }

    SURFACE_MAP = {
        'saibro': 'clay', 'rapida': 'hard', 'rápida': 'hard',
        'duro': 'hard', 'hard': 'hard', 'grama': 'grass',
        'areia': 'sand', 'carpete': 'carpet',
    }

    def _system_id(self) -> str:
        return str(self.config.get('system_id', self.SYSTEM_ID))

    def extract(self):
        payload = {
            'host': self.HOST,
            'token': '',
            'system': self._system_id(),
            'language': 'pt-BR',
            'loadAll': '1',
        }
        response = self.session.post(
            f'{self.API_BASE}{self.API_PATH}',
            data=payload,
            timeout=self._timeout,
        )
        logger.info('FPT SP API status=%s', response.status_code)
        if response.status_code >= 400:
            raise ConnectorError(f'FPT SP API returned {response.status_code}')

        data = response.json()
        if data.get('status_code') not in (0, '0'):
            raise ConnectorError(data.get('description') or 'FPT SP API error')

        seen = set()
        groups = (data.get('registers') or {}).get('list') or []
        for group in groups:
            for item in group.get('tournaments') or []:
                ext_id = item.get('id_torneio')
                if not ext_id or ext_id in seen:
                    continue
                seen.add(ext_id)
                parsed = self._normalize_item(item)
                if parsed:
                    yield parsed

    def _normalize_item(self, item: dict):
        detail_payload = self._fetch_detail_payload(item)
        detail_item = (detail_payload.get('detail') or {}) if detail_payload else {}
        local_info = ((detail_payload.get('local') or [None])[0] or {}) if detail_payload else {}
        category_items = (detail_payload.get('category') or []) if detail_payload else []
        value_items = (detail_payload.get('values') or []) if detail_payload else []

        import re as _re
        raw_title = (item.get('nome_torneio') or '').strip()
        if not raw_title:
            return None
        # FPT SP API prefixes titles with the tournament ID, e.g. "22888 - Nome do Torneio"
        title = _re.sub(r'^\d+\s*[-–]\s*', '', raw_title).strip() or raw_title

        route = (item.get('route') or '').strip()
        season_year = int(item.get('ano') or datetime.now().year)
        start_date = self.parse_date_br(detail_item.get('dt_inicio') or item.get('dt_inicio'))
        end_date = self.parse_date_br(detail_item.get('dt_final') or item.get('dt_final'))
        entry_open = self._parse_datetime(detail_item.get('dt_inicio_insc') or item.get('dt_inicio_insc'))
        entry_close = self._parse_datetime(
            detail_item.get('dt_final_insc') or item.get('dt_final_insc'),
            detail_item.get('hr_final_inscricoes') or item.get('hr_final_inscricoes') or '23:59',
        )

        # state: detail endpoint returns 'SP' (sigla), list endpoint returns 'São Paulo' (full name)
        city = (local_info.get('nome_cidade') or detail_item.get('cidade') or item.get('cidade') or '').strip()
        state_raw = local_info.get('sigla') or local_info.get('nome_uf') or detail_item.get('uf') or item.get('uf')
        state = self._normalize_state(state_raw)

        source_url = (
            detail_item.get('redirect_tenisintegrado')
            or item.get('redirect_tenisintegrado')
            or item.get('redirect_site_personal')
            or ''
        )
        modality = self._infer_modality(detail_item or item)
        status = self._infer_status(detail_item.get('descricao_situacao') or item.get('descricao_situacao'))
        categories = self._extract_categories(category_items or item)
        base_price = self._extract_base_price(value_items, categories)

        venue_name = (
            local_info.get('nome_completo')
            or local_info.get('nome_abreviado')
            or detail_item.get('por')
            or item.get('por')
            or 'FPT (SP)'
        )
        address_parts = [
            (local_info.get('endereco') or '').strip(),
            (local_info.get('numero') or '').strip(),
        ]
        address = ', '.join(part for part in address_parts if part)
        surface = self._normalize_surface(local_info)

        return {
            'external_id': f'fpt-sp:{item["id_torneio"]}',
            'canonical_name': title,
            'canonical_slug': self.slugify(f'fpt-sp-{route or "torneio"}-{item["id_torneio"]}-{title}'),
            'circuit': detail_item.get('nome_depto') or item.get('nome_depto') or 'FPT (SP)',
            'modality': modality,
            'season_year': season_year,
            'title': title,
            'start_date': start_date.isoformat() if start_date else None,
            'end_date': end_date.isoformat() if end_date else None,
            'entry_open_at': entry_open.isoformat() if entry_open else None,
            'entry_close_at': entry_close.isoformat() if entry_close else None,
            'status': status,
            'surface': surface,
            'venue': {
                'name': venue_name,
                'city': city,
                'state': state,
                'address': address,
            },
            'base_price_brl': base_price,
            'official_source_url': source_url,
            'categories': categories,
            'links': [
                {
                    'link_type': 'registration',
                    'url': source_url,
                    'label': 'Página oficial FPT (SP)',
                },
            ] if source_url else [],
        }

    def _fetch_detail_payload(self, item: dict):
        tournament_id = item.get('id_torneio')
        department_type = item.get('tipo_depto')
        if not tournament_id or not department_type:
            return {}
        payload = {
            'host': self.HOST,
            'token': '',
            'system': self._system_id(),
            'language': 'pt-BR',
            'tournamentId': str(tournament_id),
            'departmentType': str(department_type),
        }
        try:
            response = self.session.post(
                f'{self.API_BASE}{self.API_DETAIL_PATH}',
                data=payload,
                timeout=self._timeout,
            )
            logger.info('FPT SP detail API tournament=%s status=%s', tournament_id, response.status_code)
            if response.status_code >= 400:
                return {}
            data = response.json()
            if data.get('status_code') not in (0, '0'):
                return {}
            return data.get('registers') or {}
        except Exception as exc:
            logger.warning('FPT SP detail fetch failed tournament=%s exc=%s', tournament_id, exc)
            return {}

    def _parse_datetime(self, date_text: str | None, time_text: str | None = None):
        date_value = self.parse_date_br(date_text)
        if not date_value:
            return None
        hour, minute = 0, 0
        if time_text and ':' in time_text:
            try:
                hour, minute = [int(part) for part in time_text.split(':', 1)]
            except ValueError:
                pass
        return datetime(date_value.year, date_value.month, date_value.day, hour, minute)

    def _infer_modality(self, item: dict) -> str:
        return infer_modality(
            item.get('nome_torneio') or '',
            item.get('route') or '',
            item.get('nome_depto') or '',
        )

    def _infer_status(self, text: str | None) -> str:
        low = (text or '').strip().lower()
        for key, value in self.STATUS_MAP.items():
            if key in low:
                return value
        return 'announced'

    def _normalize_state(self, value: str | None) -> str:
        raw = (value or '').strip()
        if not raw:
            return ''
        if len(raw) == 2:
            return raw.upper()
        return self.STATE_MAP.get(raw.lower(), raw[:2].upper())

    def _extract_categories(self, item):
        if isinstance(item, list):
            categories = []
            for order, category in enumerate(item):
                description = (category.get('descricao') or '').strip()
                if not description:
                    continue
                notes = []
                inscritos = category.get('qtd_inscritos')
                if inscritos not in (None, ''):
                    notes.append(f'{inscritos} inscritos')
                inscricao_ate = category.get('inscrever_ate')
                if inscricao_ate:
                    notes.append(f'inscrição até {inscricao_ate}')
                categories.append({
                    'source_text': description[:200],
                    'price_brl': self.parse_price_brl(category.get('inscricao')),
                    'notes': ' • '.join(notes),
                    'order': order,
                })
            return categories

        rankings = ((item.get('grupo_pontos') or {}).get('ranking') or [])
        categories = []
        global_order = 0
        for ranking in rankings:
            name = (ranking.get('nome_ranking') or '').strip()
            groups = ranking.get('grupos') or []
            if groups:
                # Each group (age/gender combination) becomes its own category so
                # the eligibility engine can evaluate each one independently.
                for group in groups:
                    group_text = (group or '').strip()
                    if not group_text:
                        continue
                    source_text = f'{name} - {group_text}' if name else group_text
                    categories.append({
                        'source_text': source_text[:200],
                        'price_brl': None,
                        'notes': '',
                        'order': global_order,
                    })
                    global_order += 1
            elif name:
                categories.append({
                    'source_text': name[:200],
                    'price_brl': None,
                    'notes': '',
                    'order': global_order,
                })
                global_order += 1
        return categories

    def _extract_base_price(self, value_items: list, categories: list):
        public_prices = []
        for item in value_items:
            for key in ('valor_com_desconto', 'valor'):
                price = self.parse_price_brl(item.get(key))
                if price is not None:
                    public_prices.append(price)
        if public_prices:
            return min(public_prices)
        prices = [c.get('price_brl') for c in categories if c.get('price_brl') is not None]
        return min(prices) if prices else None

    def _normalize_surface(self, local_info: dict):
        for key in ('tipo_piso_1', 'tipo_piso_2', 'tipo_piso_3'):
            raw = (local_info.get(key) or '').strip().lower()
            if not raw:
                continue
            return self.SURFACE_MAP.get(raw, 'unknown')
        return 'unknown'


@register_connector
class FPTSPKidsConnector(FPTSPPublicConnector):
    """
    FPT (SP) Tennis Kids circuit only.

    departmentType=7 returns only the Kids department. Useful when a dedicated
    DataSource/schedule is needed for the Kids circuit without fetching all depts.
    """

    key = 'fpt_sp_kids'
    DEPARTMENT_TYPE_KIDS = '7'

    def extract(self):
        payload = {
            'host': self.HOST,
            'token': '',
            'system': self._system_id(),
            'language': 'pt-BR',
            'departmentType': self.config.get('department_type', self.DEPARTMENT_TYPE_KIDS),
        }
        response = self.session.post(
            f'{self.API_BASE}{self.API_PATH}',
            data=payload,
            timeout=self._timeout,
        )
        logger.info('FPT SP Kids API status=%s', response.status_code)
        if response.status_code >= 400:
            raise ConnectorError(f'FPT SP Kids API returned {response.status_code}')

        data = response.json()
        if data.get('status_code') not in (0, '0'):
            raise ConnectorError(data.get('description') or 'FPT SP Kids API error')

        seen = set()
        groups = (data.get('registers') or {}).get('list') or []
        for group in groups:
            for item in group.get('tournaments') or []:
                ext_id = item.get('id_torneio')
                if not ext_id or ext_id in seen:
                    continue
                seen.add(ext_id)
                parsed = self._normalize_item(item)
                if parsed:
                    yield parsed
