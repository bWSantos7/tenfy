"""
CBT connector backed by the public Tennis Tool API.

The website is now a SPA and no longer exposes tournament cards in the
server-rendered HTML, but the data still comes from the public API below.
"""
import logging
from datetime import datetime

from .base import BaseConnector, ConnectorError, register_connector

logger = logging.getLogger('apps.ingestion.cbt')


@register_connector
class CBTPublicConnector(BaseConnector):
    key = 'cbt_public'

    API_BASE = 'https://api.tennistool.tenisintegrado.com'
    API_PATH = '/tournaments/tournament/getTournamentDepartmentList'
    API_DETAIL_PATH = '/tournaments/tournament/getTournament'
    SYSTEM_ID = '2'
    HOST = 'cbt-tenis.com.br'

    STATUS_MAP = {
        'inscricoes abertas': 'open',
        'inscrições abertas': 'open',
        'encerrando em breve': 'closing_soon',
        'inscricoes encerradas': 'closed',
        'inscrições encerradas': 'closed',
        'torneio iniciado': 'in_progress',
        'em andamento': 'in_progress',
        'chaves publicadas': 'draws_published',
        'torneio encerrado': 'finished',
        'finalizado': 'finished',
        'cancelado': 'canceled',
    }

    STATE_MAP = {
        'acre': 'AC',
        'alagoas': 'AL',
        'amapa': 'AP',
        'amapá': 'AP',
        'amazonas': 'AM',
        'bahia': 'BA',
        'ceara': 'CE',
        'ceará': 'CE',
        'distrito federal': 'DF',
        'espirito santo': 'ES',
        'espírito santo': 'ES',
        'goias': 'GO',
        'goiás': 'GO',
        'maranhao': 'MA',
        'maranhão': 'MA',
        'mato grosso': 'MT',
        'mato grosso do sul': 'MS',
        'minas gerais': 'MG',
        'para': 'PA',
        'pará': 'PA',
        'paraiba': 'PB',
        'paraíba': 'PB',
        'parana': 'PR',
        'paraná': 'PR',
        'pernambuco': 'PE',
        'piaui': 'PI',
        'piauí': 'PI',
        'rio de janeiro': 'RJ',
        'rio grande do norte': 'RN',
        'rio grande do sul': 'RS',
        'rondonia': 'RO',
        'rondônia': 'RO',
        'roraima': 'RR',
        'santa catarina': 'SC',
        'sao paulo': 'SP',
        'são paulo': 'SP',
        'sergipe': 'SE',
        'tocantins': 'TO',
    }

    SURFACE_MAP = {
        'saibro': 'clay',
        'rapida': 'hard',
        'rápida': 'hard',
        'duro': 'hard',
        'hard': 'hard',
        'grama': 'grass',
        'areia': 'sand',
        'carpete': 'carpet',
    }

    def extract(self):
        payload = {
            'host': self.HOST,
            'token': '',
            'system': self.SYSTEM_ID,
            'language': 'pt-BR',
            'loadAll': '1',
        }
        response = self.session.post(
            f'{self.API_BASE}{self.API_PATH}',
            data=payload,
            timeout=self._timeout,
        )
        logger.info('CBT API status=%s', response.status_code)
        if response.status_code >= 400:
            raise ConnectorError(f'CBT API returned {response.status_code}')

        data = response.json()
        if data.get('status_code') not in (0, '0'):
            raise ConnectorError(data.get('description') or 'CBT API error')

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

        title = (item.get('nome_torneio') or '').strip()
        if not title:
            return None

        route = (item.get('route') or '').strip()
        season_year = int(item.get('ano') or datetime.now().year)
        start_date = self.parse_date_br(detail_item.get('dt_inicio') or item.get('dt_inicio'))
        end_date = self.parse_date_br(detail_item.get('dt_final') or item.get('dt_final'))
        entry_open = self._parse_datetime(detail_item.get('dt_inicio_insc') or item.get('dt_inicio_insc'))
        entry_close = self._parse_datetime(
            detail_item.get('dt_final_insc') or item.get('dt_final_insc'),
            detail_item.get('hr_final_inscricoes') or item.get('hr_final_inscricoes') or '23:59',
        )
        city = (local_info.get('nome_cidade') or detail_item.get('cidade') or item.get('cidade') or '').strip()
        state = self._normalize_state(local_info.get('sigla') or local_info.get('nome_uf') or detail_item.get('uf') or item.get('uf'))
        source_url = detail_item.get('redirect_tenisintegrado') or item.get('redirect_tenisintegrado') or item.get('redirect_site_personal') or ''
        modality = self._infer_modality(detail_item or item)
        status = self._infer_status(detail_item.get('descricao_situacao') or item.get('descricao_situacao'))
        categories = self._extract_categories(category_items or item)
        base_price = self._extract_base_price(value_items, categories)
        venue_name = (
            local_info.get('nome_completo')
            or local_info.get('nome_abreviado')
            or detail_item.get('por')
            or item.get('por')
            or 'CBT'
        )
        address_parts = [
            (local_info.get('endereco') or '').strip(),
            (local_info.get('numero') or '').strip(),
        ]
        address = ', '.join(part for part in address_parts if part)
        surface = self._normalize_surface(local_info)

        return {
            'external_id': f'cbt:{item["id_torneio"]}',
            'canonical_name': title,
            'canonical_slug': self.slugify(f'cbt-{route or "tournament"}-{item["id_torneio"]}-{title}'),
            'circuit': detail_item.get('nome_depto') or item.get('nome_depto') or 'CBT',
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
                    'label': 'Página oficial CBT',
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
            'system': self.SYSTEM_ID,
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
            logger.info('CBT detail API tournament=%s status=%s', tournament_id, response.status_code)
            if response.status_code >= 400:
                return {}
            data = response.json()
            if data.get('status_code') not in (0, '0'):
                return {}
            return data.get('registers') or {}
        except Exception as exc:
            logger.warning('CBT detail fetch failed tournament=%s exc=%s', tournament_id, exc)
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
                hour, minute = 0, 0
        return datetime(date_value.year, date_value.month, date_value.day, hour, minute)

    def _infer_modality(self, item: dict) -> str:
        route = (item.get('route') or '').lower()
        department = (item.get('nome_depto') or '').lower()
        if 'beach' in route or 'beach' in department:
            return 'beach_tennis'
        if 'wheelchair' in route or 'cadeira' in department:
            return 'wheelchair'
        return 'tennis'

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

    def _extract_categories(self, item: dict):
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
        for order, ranking in enumerate(rankings):
            name = (ranking.get('nome_ranking') or '').strip()
            groups = ranking.get('grupos') or []
            source_text = ' - '.join(part for part in [name, ', '.join(groups)] if part)
            if not source_text:
                continue
            categories.append({
                'source_text': source_text[:200],
                'price_brl': None,
                'notes': '',
                'order': order,
            })
        return categories

    def _extract_base_price(self, value_items: list[dict], categories: list[dict]):
        public_prices = []
        for item in value_items:
            for key in ('valor_com_desconto', 'valor'):
                price = self.parse_price_brl(item.get(key))
                if price is not None:
                    public_prices.append(price)
        if public_prices:
            return min(public_prices)

        prices = [c.get('price_brl') for c in categories if c.get('price_brl') is not None]
        if not prices:
            return None
        return min(prices)

    def _normalize_surface(self, local_info: dict):
        for key in ('tipo_piso_1', 'tipo_piso_2', 'tipo_piso_3'):
            raw = (local_info.get(key) or '').strip().lower()
            if not raw:
                continue
            return self.SURFACE_MAP.get(raw, 'unknown')
        return 'unknown'
