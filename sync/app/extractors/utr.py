"""UTR Sports - torneios no Brasil via API pública de busca de eventos.

Endpoint: https://api.utrsports.net/v2/search/events (GET, paginado por top/skip).
A API não expõe filtro de país server-side estável, então usamos uma busca
textual ("Brazil" + termos) e filtramos client-side por countryCode2 == 'BR'.

Os inscritos vêm do campo ``registeredMembers`` de cada evento na própria busca
(nome + memberId), disponível inclusive sem autenticação. Se houver credenciais
(UTR_EMAIL/UTR_PASSWORD), fazemos login para autenticar a sessão (dados mais
completos em alguns endpoints).
"""
from __future__ import annotations

import json
from typing import Iterator, List, Optional

from app.config import settings
from app.schemas import ExtractedCategory, ExtractedEntrant, ExtractedTournament
from app.utils.dates import parse_date
from app.utils.money import parse_money
from app.utils.text import clean_spaces
from app.extractors.base import BaseTournamentExtractor

SEARCH_URL = "https://api.utrsports.net/v2/search/events"
LOGIN_URL = "https://app.utrsports.net/api/v1/auth/login"
SITE_BASE = "https://app.utrsports.net"

# Consultas textuais usadas para varrer eventos brasileiros.
QUERIES = ["Brazil", "Brasil", "Brasileiro", "Junior Brazil", "Tenis"]


class UtrExtractor(BaseTournamentExtractor):
    name = "utr"
    base_url = "https://app.utrsports.net/brazil/tennis-tournaments"
    source_type = "api"
    PAGE_SIZE = 50
    MAX_PAGES_PER_QUERY = 10

    def _login(self) -> None:
        """Autentica a sessão se houver credenciais (opcional)."""
        if not (settings.utr_email and settings.utr_password):
            return
        try:
            self.http.post(
                LOGIN_URL,
                data=json.dumps({"email": settings.utr_email, "password": settings.utr_password}),
                headers={"Content-Type": "application/json", "Origin": SITE_BASE,
                         "Referer": SITE_BASE + "/"},
            )
            self.logger.info("UTR: sessão autenticada para %s", settings.utr_email)
        except Exception as exc:
            self._record_error(f"Falha no login UTR (seguindo sem auth): {exc}",
                               "LoginError", url=LOGIN_URL, exc=exc)

    def fetch_tournaments(self) -> Iterator[ExtractedTournament]:
        self._login()
        seen: set = set()
        for query in QUERIES:
            for page in range(self.MAX_PAGES_PER_QUERY):
                params = {
                    "query": query,
                    "top": self.PAGE_SIZE,
                    "skip": page * self.PAGE_SIZE,
                    "searchOrigin": "tournamentSearch",
                }
                try:
                    data = self.http.get_json(SEARCH_URL, params=params,
                                              headers={"Accept": "application/json"})
                except Exception as exc:
                    self._record_error(f"Falha busca UTR '{query}' p{page}: {exc}",
                                       "FetchError", url=SEARCH_URL, exc=exc)
                    break
                hits = data.get("hits", []) if isinstance(data, dict) else []
                if not hits:
                    break
                for hit in hits:
                    src = hit.get("source") or hit.get("_source") or {}
                    loc = (src.get("eventLocations") or [{}])[0]
                    if (loc.get("countryCode2") or "").upper() != "BR":
                        continue  # mantém só Brasil
                    eid = str(src.get("id") or hit.get("id") or "")
                    if not eid or eid in seen:
                        continue
                    seen.add(eid)
                    try:
                        t = self._parse(src, loc, eid)
                        if t:
                            yield t
                    except Exception as exc:
                        self._record_error(f"Falha ao parsear evento UTR {eid}: {exc}",
                                           "ParseError", exc=exc)

    def _parse(self, src: dict, loc: dict, eid: str) -> ExtractedTournament:
        sched = src.get("eventSchedule") or {}
        name = clean_spaces(src.get("name") or "")

        # Categorias/divisões.
        categories: List[ExtractedCategory] = []
        for div in src.get("eventDivisions") or []:
            dname = clean_spaces(div.get("name") or "")
            if dname:
                categories.append(ExtractedCategory(name=dname, raw_data={"id": div.get("id")}))

        # Inscritos: a busca já traz a lista nominal em ``registeredMembers``
        # (nome + memberId). Não há divisão/situação por inscrito nesse campo,
        # então ficam no nível do torneio (category_name=None).
        reg_count = src.get("registeredCount") or src.get("registrationsCount")
        entrants: List[ExtractedEntrant] = []
        if self.fetch_entrants:
            for i, m in enumerate(src.get("registeredMembers") or [], start=1):
                if not isinstance(m, dict):
                    continue
                entrant_name = clean_spaces(
                    " ".join(filter(None, [m.get("firstName"), m.get("lastName")]))
                ) or clean_spaces(m.get("displayName") or "")
                if not entrant_name:
                    continue
                entrants.append(ExtractedEntrant(
                    external_id=str(m.get("memberId") or m.get("id") or ""),
                    name=entrant_name,
                    country=loc.get("countryName") or "Brasil",
                    position=i,
                    registration_status="inscrito",
                    raw_data=m,
                ))

        club = src.get("club") or {}
        utr_range = src.get("utrRange") or {}

        # eventState é um objeto aninhado: extrai o rótulo legível.
        ev_state = src.get("eventState")
        if isinstance(ev_state, dict):
            ev_state = ev_state.get("label") or ev_state.get("value")
        rating = None
        if isinstance(utr_range, dict) and (utr_range.get("min") or utr_range.get("max")):
            rating = f"{utr_range.get('min', '')}-{utr_range.get('max', '')}".strip("-")

        return ExtractedTournament(
            external_id=eid,
            name=name,
            original_name=name,
            federation="UTR",
            organization=clean_spaces(club.get("name") or "") or "UTR Sports",
            modality="tennis",
            country=loc.get("countryName") or "Brasil",
            state=loc.get("stateAbbr") or loc.get("stateName"),
            city=self._city_from_location(loc),
            venue=clean_spaces(club.get("name") or ""),
            address=loc.get("googleFormattedName"),
            start_date=parse_date((sched.get("eventStartUtc") or "")[:10]),
            end_date=parse_date((sched.get("eventEndUtc") or "")[:10]),
            registration_start_date=parse_date((sched.get("registrationStartUtc") or "")[:10]),
            registration_end_date=parse_date((sched.get("registrationEndUtc") or "")[:10]),
            registration_fee=parse_money(src.get("entryFee") or src.get("priceRangeShort")),
            status=ev_state,
            original_url=f"{SITE_BASE}/events/{eid}",
            categories=categories,
            entrants=entrants,
            raw_data={
                "id": eid, "name": name, "gender": src.get("gender"),
                "registeredCount": reg_count, "utrRange": utr_range,
                "rating": rating, "location": loc, "schedule": sched,
            },
        )

    @staticmethod
    def _city_from_location(loc: dict) -> Optional[str]:
        """Prefere cityName; evita usar logradouro (Av./Rua) como cidade."""
        city = clean_spaces(loc.get("cityName") or "")
        if city:
            return city
        first = clean_spaces((loc.get("display") or "").split(",")[0])
        if not first or first[:4].lower() in ("av. ", "av ", "rua ", "r. ", "al. ", "rod."):
            return None
        return first or None
