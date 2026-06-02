"""
UTR (Universal Tennis Rating) integration.

Extraction strategy:

1. search_utr_players(name)
   → hits[].source via UTR search API (requests only)
   → returns candidates with name, location, singlesUtrDisplay, doublesUtrDisplay

2. scrape_utr_profile_rating(player_id, player_name)
   → opens https://app.utrsports.net/profiles/{id} with Playwright
   → extracts rating from the rendered DOM (same logic as utr_ranking.py)
   → called from Celery task after user confirms a profile

Railway note:
  - requests-only functions run on web + worker.
  - Playwright functions run ONLY on the Celery worker (needs `playwright install chromium`).
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

import requests

logger = logging.getLogger('apps.players.utr')

UTR_SEARCH_URL   = 'https://api.utrsports.net/v2/search/players'
UTR_PROFILE_BASE = 'https://app.utrsports.net/profiles'

_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Origin': 'https://app.utrsports.net',
    'Referer': 'https://app.utrsports.net/',
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _clean(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _get(data: dict, *keys: str) -> Any:
    """Return first non-empty value found among the given dot-notation paths."""
    for key in keys:
        current: Any = data
        found = True
        for part in key.split('.'):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                found = False
                break
        if found and current not in (None, '', 0):
            return current
    return None


def _normalize_rating(value: Any) -> Optional[str]:
    """
    Accepts:
      - numeric float: 4.35  → '4.35'
      - string '4.35'        → '4.35'
      - display string '4.xx'→ '4.xx'  (masked — UTR requires subscription to show real value)
    Returns None for 0, unrated, or unparseable.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        n = float(value)
        if 1.0 <= n <= 16.5:
            return f'{n:.2f}'
        return None
    text = _clean(value).replace(',', '.')
    # Real numeric
    for item in re.findall(r'\b(?:1[0-6]|[1-9])\.\d{1,2}\b', text):
        try:
            if 1.0 <= float(item) <= 16.5:
                return item
        except ValueError:
            continue
    # Masked display (4.xx / 10.xx)
    masked = re.findall(r'\b(?:1[0-6]|[1-9])\.(?:x{2}|X{2})\b', text)
    if masked:
        return masked[0].lower()
    return None


def _find_all_ratings(text: str, keep_duplicates: bool = True) -> list[str]:
    """Find all rating strings in a block of text (preserves duplicates for singles/doubles)."""
    text = _clean(text).replace(',', '.')
    results: list[str] = []
    for pattern in (r'\b(?:1[0-6]|[1-9])\.\d{1,2}\b', r'\b(?:1[0-6]|[1-9])\.(?:x{2}|X{2})\b'):
        for m in re.findall(pattern, text):
            normalized = m.lower()
            if keep_duplicates or normalized not in results:
                results.append(normalized)
    return results


def _parse_hit(hit: dict[str, Any], index: int) -> Optional[dict[str, Any]]:
    """
    Parse a single hit from the UTR search response.
    The actual player data lives in hit['source'].
    """
    source = hit.get('source') or hit  # fallback to root if already flattened

    player_id = _get(source, 'id', 'profileId', 'playerId')
    if player_id is None:
        player_id = hit.get('id')
    if player_id is None:
        return None
    player_id = str(player_id)

    first = _clean(_get(source, 'firstName', 'playerFirstName') or '')
    last  = _clean(_get(source, 'lastName',  'playerLastName')  or '')
    display_name = _clean(
        _get(source, 'displayName', 'fullName', 'name') or f'{first} {last}'.strip()
    ) or f'Perfil UTR {player_id}'

    # singlesUtrDisplay / doublesUtrDisplay are the display values the app shows
    singles = _normalize_rating(
        _get(source, 'singlesUtrDisplay', 'myUtrSinglesDisplay', 'singlesUtr', 'myUtrSingles')
    )
    doubles = _normalize_rating(
        _get(source, 'doublesUtrDisplay', 'myUtrDoublesDisplay', 'doublesUtr', 'myUtrDoubles')
    )

    location_obj = source.get('location') or {}
    location = _clean(
        _get(source, 'descriptionShort')
        or _get(location_obj, 'display', 'countryName', 'stateName', 'cityName')
        or _get(source, 'nationality', 'birthPlace', 'homeClub')
        or ''
    )

    return {
        'index':        index,
        'utr_player_id': player_id,
        'display_name': display_name,
        'country':      _clean(_get(location_obj, 'countryName') or _get(source, 'nationality') or ''),
        'location':     location,
        'gender':       _clean(_get(source, 'gender') or ''),
        'singles_utr':  singles,
        'doubles_utr':  doubles,
        'rating_status': _clean(
            _get(source, 'ratingStatusSingles', 'ratingStatusDoubles', 'ratingStatus') or ''
        ),
        'profile_url':  f'{UTR_PROFILE_BASE}/{player_id}',
    }


# ── public: search ────────────────────────────────────────────────────────────

def search_utr_players(
    name: str,
    max_results: int = 8,
    timeout: int = 25,
    retries: int = 2,
) -> list[dict[str, Any]]:
    """
    Search UTR public search API by player name.
    Returns candidate list with display-quality data (names, location, display ratings).
    Ratings may be masked (e.g. '4.xx') — use scrape_utr_profile_rating for the real value.
    """
    query = _clean(name)
    if not query:
        raise ValueError('Nome vazio.')

    last_error: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(
                UTR_SEARCH_URL,
                params={'query': query},
                headers=_HEADERS,
                timeout=timeout,
            )
            resp.raise_for_status()
            payload = resp.json()

            # The response is { "hits": [ { "id": "...", "source": {...} }, ... ] }
            hits = payload.get('hits') or []
            if not hits and isinstance(payload, list):
                hits = payload

            candidates: list[dict[str, Any]] = []
            for hit in hits:
                if not isinstance(hit, dict):
                    continue
                parsed = _parse_hit(hit, index=len(candidates) + 1)
                if parsed:
                    candidates.append(parsed)
                if len(candidates) >= max_results:
                    break

            logger.info('UTR search "%s" → %d candidates', query, len(candidates))
            return candidates

        except Exception as exc:
            last_error = exc
            logger.warning('UTR search attempt %d/%d failed: %s', attempt, retries, exc)
            if attempt < retries:
                time.sleep(2)

    raise RuntimeError(f'Busca UTR falhou após {retries} tentativas: {last_error}')


# ── public: Playwright rating extraction ─────────────────────────────────────

def scrape_utr_profile_rating(
    player_id: str,
    player_name: str = '',
    timeout_ms: int = 45000,
) -> dict[str, Any]:
    """
    Open the confirmed UTR profile page with a headless Chromium browser and
    extract singles + doubles UTR ratings from the rendered DOM.

    Replicates the extraction logic from utr_ranking.py:
      Priority: 1. header DOM position  2. full body text  3. none

    Requires on the Celery worker:
      pip install playwright
      playwright install chromium

    Returns: { success, singles_utr, doubles_utr, display_name, extraction_method, error }
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        return {
            'success': False,
            'singles_utr': None,
            'doubles_utr': None,
            'display_name': player_name,
            'extraction_method': None,
            'error': 'Playwright não instalado no worker.',
        }

    profile_url = f'{UTR_PROFILE_BASE}/{player_id}'
    display_name_found: Optional[str] = player_name

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                ],
            )
            ctx = browser.new_context(
                viewport={'width': 1440, 'height': 1200},
                user_agent=(
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/124.0.0.0 Safari/537.36'
                ),
                locale='en-US',
            )
            page = ctx.new_page()
            page.goto(profile_url, wait_until='domcontentloaded', timeout=timeout_ms)
            try:
                page.wait_for_load_state('networkidle', timeout=15000)
            except PlaywrightTimeout:
                pass

            # Accept / close cookie banners (same as utr_ranking.py)
            _handle_cookies(page)
            page.wait_for_timeout(6000)
            _handle_cookies(page)
            page.wait_for_timeout(1500)

            # ── Display name ─────────────────────────────────────────────────
            for sel in ('h1', "[data-testid*='name' i]", "[class*='name' i]"):
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0:
                        val = _clean(loc.inner_text(timeout=3000))
                        if val and len(val) <= 100:
                            display_name_found = val
                            break
                except Exception:
                    continue
            if not display_name_found:
                try:
                    title = _clean(page.title())
                    display_name_found = title.replace('| UTR Sports', '').replace('UTR Sports', '').strip(' -|')
                except Exception:
                    pass

            # ── Strategy 1: header DOM by visual position ────────────────────
            # The page renders two UTR cards in the header:
            #   first card  = singles  (individual icon)
            #   second card = doubles  (two-people icon)
            # We collect text from header/profile selectors and take the first
            # two rating values found, preserving duplicates (e.g. both "4.xx").
            header_snippets: list[str] = []
            for sel in ('header', 'main', 'body',
                        "[class*='profile' i]", "[class*='rating' i]", "[class*='utr' i]"):
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0:
                        txt = _clean(loc.inner_text(timeout=3000))
                        if txt and txt not in header_snippets:
                            header_snippets.append(txt)
                except Exception:
                    continue

            combined_header = ' '.join(header_snippets)
            header_ratings = _find_all_ratings(combined_header, keep_duplicates=True)

            singles_from_header: Optional[str] = header_ratings[0] if len(header_ratings) >= 1 else None
            doubles_from_header: Optional[str] = header_ratings[1] if len(header_ratings) >= 2 else None

            # ── Strategy 2: infer from body text using "Singles"/"Doubles" labels ─
            page_text = ''
            try:
                page_text = _clean(page.locator('body').inner_text(timeout=10000))
            except Exception:
                pass

            singles_from_dom, doubles_from_dom = _infer_ratings_from_text(
                header_snippets + ([page_text] if page_text else [])
            )

            browser.close()

        # ── Priority: header DOM position > DOM text inference ───────────────
        final_singles: Optional[str] = None
        final_doubles: Optional[str] = None
        extraction_method: Optional[str] = None

        if singles_from_header or doubles_from_header:
            final_singles     = singles_from_header
            final_doubles     = doubles_from_header
            extraction_method = 'header_dom_position'
        elif singles_from_dom or doubles_from_dom:
            final_singles     = singles_from_dom
            final_doubles     = doubles_from_dom
            extraction_method = 'dom_text'

        if final_singles or final_doubles:
            return {
                'success':          True,
                'singles_utr':      final_singles,
                'doubles_utr':      final_doubles,
                'display_name':     display_name_found,
                'extraction_method': extraction_method,
                'error':            None,
            }

        return {
            'success':          False,
            'singles_utr':      None,
            'doubles_utr':      None,
            'display_name':     display_name_found,
            'extraction_method': None,
            'error': (
                'Perfil confirmado, cookies tratados, mas rating não encontrado '
                'no DOM após renderização. O perfil pode exigir login UTR para exibir o valor.'
            ),
        }

    except Exception as exc:
        return {
            'success':          False,
            'singles_utr':      None,
            'doubles_utr':      None,
            'display_name':     display_name_found,
            'extraction_method': None,
            'error':            f'{type(exc).__name__}: {exc}',
        }


def _infer_ratings_from_text(snippets: list[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Try to infer singles + doubles from text snippets using 'Singles'/'Doubles' labels.
    Falls back to first/second rating found if labels are absent.
    Mirrors infer_ratings_from_candidates() in utr_ranking.py.
    """
    singles: Optional[str] = None
    doubles: Optional[str] = None

    for snippet in snippets:
        lower = snippet.lower()
        if singles is None and ('singles' in lower or 'single' in lower):
            singles = _normalize_rating(snippet)
        if doubles is None and ('doubles' in lower or 'double' in lower):
            doubles = _normalize_rating(snippet)

    if singles is None or doubles is None:
        all_ratings: list[str] = []
        for snippet in snippets:
            all_ratings.extend(_find_all_ratings(snippet, keep_duplicates=True))
        if singles is None and len(all_ratings) >= 1:
            singles = all_ratings[0]
        if doubles is None and len(all_ratings) >= 2:
            doubles = all_ratings[1]

    return singles, doubles


def _handle_cookies(page: Any) -> None:
    """Accept/close UTR cookie banners — mirrors handle_cookie_banners() in utr_ranking.py."""
    import re as _re
    page.wait_for_timeout(800)
    for name in ('Allow All', 'Save & Accept', 'Accept All', 'Accept', 'I Agree', 'Got it', 'OK'):
        try:
            btn = page.get_by_role('button', name=_re.compile(name, _re.IGNORECASE)).first
            if btn.count() > 0 and btn.is_visible(timeout=1200):
                btn.click(timeout=1500)
                page.wait_for_timeout(800)
        except Exception:
            pass
    for name in ('Allow All', 'Save & Accept', 'Accept All', 'Accept'):
        try:
            loc = page.get_by_text(_re.compile(name, _re.IGNORECASE)).first
            if loc.count() > 0 and loc.is_visible(timeout=800):
                loc.click(timeout=1000)
                page.wait_for_timeout(700)
        except Exception:
            pass
    for sel in ("button[aria-label='Close']", "[aria-label='close']", "button:has-text('×')"):
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=800):
                loc.click(timeout=1000)
        except Exception:
            pass
    # Last attempt: scan all buttons for accept text
    try:
        for btn in page.locator('button').all():
            try:
                text = _clean(btn.inner_text(timeout=400))
                if _re.search(r'Allow All|Save & Accept|Accept', text, _re.IGNORECASE):
                    if btn.is_visible(timeout=400):
                        btn.click(timeout=800)
                        page.wait_for_timeout(600)
            except Exception:
                continue
    except Exception:
        pass
