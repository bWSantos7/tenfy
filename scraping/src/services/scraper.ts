import { Browser, Page, chromium } from 'playwright';
import { Player } from '../models/Player';
import { RankingEntry } from '../models/RankingEntry';
import { Tournament, VALID_UF } from '../models/Tournament';

const BASE_URL = 'https://cosat.tournamentsoftware.com';
const headless = process.env.HEADLESS !== 'false';
const scrapeRetries = Number(process.env.SCRAPE_RETRIES || 2);

// ---------------------------------------------------------------------------
// Location parsing helpers
// ---------------------------------------------------------------------------

/**
 * Parse a COSAT location string like "São Paulo, SP" or "Cidade - UF"
 * into separate city and state fields.
 */
function parseLocationBR(location: string): { city: string; state: string } {
    if (!location) return { city: '', state: '' };

    // Remove anything that looks like a country suffix (e.g., ", BRA", ", Brazil")
    const cleaned = location.replace(/,?\s*(BRA|BRZ|Brazil|Brasil)$/i, '').trim();

    // Pattern: "City, UF" or "City - UF" or "City (UF)"
    const explicit = cleaned.match(/^(.+?)[\s,\-–]+([A-Z]{2})\s*(?:\(.*\))?$/);
    if (explicit && VALID_UF.has(explicit[2])) {
        return { city: explicit[1].trim(), state: explicit[2] };
    }

    // Pattern: any 2-char uppercase word that is a valid UF
    const anyUf = cleaned.match(/\b([A-Z]{2})\b/);
    const uf = anyUf && VALID_UF.has(anyUf[1]) ? anyUf[1] : '';
    const city = uf
        ? cleaned.replace(new RegExp(`[,\\s\\-–]+${uf}\\b`), '').trim()
        : cleaned;

    return { city, state: uf };
}

/**
 * Returns true if the text looks like an email address.
 */
function isEmail(text: string): boolean {
    return /[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z0-9_-]+/.test(text);
}

/**
 * Returns true if a location string is valid (not an email, not too short).
 */
function isValidLocation(text: string): boolean {
    if (!text || text.length < 3) return false;
    if (isEmail(text)) return false;
    if (/^\d{5}-\d{3}$/.test(text.trim())) return false; // CEP puro
    return true;
}

/**
 * Infer modality from tournament name and organization.
 * COSAT is predominantly tennis; explicit keywords override.
 */
function inferModality(name: string, organization: string = ''): string {
    const combined = (name + ' ' + organization).toLowerCase();
    if (/beach\s*tennis|beach/.test(combined)) return 'beach_tennis';
    if (/padel/.test(combined)) return 'padel';
    if (/cadeirante|wheelchair/.test(combined)) return 'wheelchair';
    return 'tennis';
}

/**
 * Validate extracted tournament data and return list of error codes.
 */
function validateTournament(data: {
    cosatId?: string;
    name?: string;
    location?: string;
    state?: string;
    tournament_start_at?: string;
    tournament_end_at?: string;
}): string[] {
    const errors: string[] = [];
    if (!data.cosatId) errors.push('missing_cosatId');
    if (!data.name || data.name.length < 3) errors.push('invalid_name');
    if (data.location && isEmail(data.location)) errors.push('email_in_location');
    if (data.state && !VALID_UF.has(data.state)) errors.push('invalid_state');
    if (data.tournament_start_at && data.tournament_end_at) {
        if (data.tournament_end_at < data.tournament_start_at) {
            errors.push('end_before_start');
        }
    }
    return errors;
}

type TournamentListItem = {
    cosatId: string;
    name: string;
    url: string;
    organization?: string;
    location?: string;
    country?: string;
    dateRange?: string;
    hasOnlineEntry?: boolean;
};

type TournamentDetails = {
    organization?: string;
    location?: string;
    country?: string;
    dateRange?: string;
    registration_open_at?: string;
    registration_close_at?: string;
    withdrawal_deadline_at?: string;
    tournament_start_at?: string;
    tournament_end_at?: string;
    timezone?: string;
    source_dates_raw?: any;
    categoriesCount?: number;
    entriesCount?: number;
};

type TournamentEvent = {
    eventId?: string;
    name: string;
    draws?: number;
    entries?: number;
};

type TournamentPlayer = {
    name: string;
    country?: string;
    countryCode?: string;
    tournamentId: string;
    tournamentName: string;
    tournamentPlayerId?: string;
};

type RankingData = {
    rankingId?: string;
    rankingDate?: string;
    updatedText?: string;
    sourceUrl: string;
    entries: RankingEntryData[];
};

type RankingCategory = {
    name: string;
    url: string;
};

type RankingEntryData = {
    category: string;
    rank: number;
    playerName: string;
    playerId?: string;
    profileId?: string;
    country?: string;
    dob?: string;
    singlesPoints?: string;
    doublesPoints?: string;
    bonusPoints?: string;
    totalPoints?: string;
};

function getLastPathPart(url: string) {
    return new URL(url, BASE_URL).pathname.split('/').filter(Boolean).pop();
}

function getSearchParam(url: string, param: string) {
    return new URL(url, BASE_URL).searchParams.get(param) || undefined;
}

function toNumber(value?: string) {
    if (!value) return undefined;
    const parsed = Number(value.replace(/\D/g, ''));
    return Number.isFinite(parsed) ? parsed : undefined;
}

function formatDateParam(date: Date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');

    return `${year}-${month}-${day}`;
}

async function newScrapingPage(browser: Browser) {
    const context = await browser.newContext({
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    });

    await context.route('**/*', async route => {
        const resourceType = route.request().resourceType();

        if (['font', 'image', 'media'].includes(resourceType)) {
            await route.abort();
            return;
        }

        await route.continue();
    });

    const page = await context.newPage();
    page.setDefaultNavigationTimeout(20000);
    page.setDefaultTimeout(15000);

    return { context, page };
}

async function withScrapingPage<T>(browser: Browser, action: (page: Page) => Promise<T>) {
    const { context, page } = await newScrapingPage(browser);

    try {
        return await action(page);
    } finally {
        await context.close().catch(() => undefined);
    }
}

async function withRetry<T>(description: string, action: () => Promise<T>) {
    let lastError: unknown;

    for (let attempt = 1; attempt <= scrapeRetries; attempt++) {
        try {
            return await action();
        } catch (error) {
            lastError = error;
            console.error(`Falha em ${description} (tentativa ${attempt}/${scrapeRetries}):`, error);
        }
    }

    throw lastError;
}

function buildTournamentSearchUrl() {
    const startDate = new Date();
    const endDate = new Date(startDate);
    endDate.setDate(endDate.getDate() + 365);

    const url = new URL('/find', BASE_URL);
    url.searchParams.set('DateFilterType', '0');
    url.searchParams.set('StartDate', formatDateParam(startDate));
    url.searchParams.set('EndDate', formatDateParam(endDate));

    return url.href;
}

async function scrapeTournamentList(page: Page): Promise<TournamentListItem[]> {
    await page.goto(buildTournamentSearchUrl(), { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(3000);
    
    try {
        await page.waitForSelector('.media__link[href*="tournament"]', { timeout: 15000 });
    } catch (e) {
        console.log("Nenhum torneio encontrado na lista.");
        return [];
    }

    let hasMore = true;
    let attempts = 0;
    while (hasMore && attempts < 20) {
        try {
            const btnSelector = 'button.js-pagination-load-more, .btn-load-more, button:has-text("Load more"), button:has-text("Carregar mais"), button:has-text("Cargar más")';
            const loadMoreBtn = await page.$(btnSelector);
            
            if (loadMoreBtn) {
                const isVisible = await loadMoreBtn.isVisible();
                if (isVisible) {
                    console.log("Clicando no botao Carregar Mais...");
                    await page.evaluate(btn => (btn as HTMLElement).click(), loadMoreBtn);
                    await page.waitForTimeout(2000);
                    attempts++;
                } else {
                    hasMore = false;
                }
            } else {
                hasMore = false;
            }
        } catch (e) {
            console.log("Erro ao clicar em carregar mais, finalizando paginacao:", e instanceof Error ? e.message : e);
            hasMore = false;
        }
    }

    return page.$$eval('.list--bordered > .list__item', items => {
        return items.flatMap(item => {
            const link = item.querySelector<HTMLAnchorElement>('.media__link[href*="tournament"]');
            if (!link) return [];

            const href = link.getAttribute('href') || '';
            const tournamentUrl = new URL(href, window.location.origin);
            const cosatId = tournamentUrl.searchParams.get('id') || tournamentUrl.pathname.split('/').filter(Boolean).pop() || '';
            const name = link.textContent?.trim() || '';
            if (!cosatId || !name) return [];

            const subheadings = Array.from(item.querySelectorAll('.media__subheading')).map(el => (
                el.textContent || ''
            ).trim().replace(/\s+/g, ' ')).filter(Boolean);
            const locationText = subheadings.find(text => text.includes('|'));
            const locationParts = locationText?.split('|').map(part => part.trim()) || [];
            const location = locationParts[1];
            const country = location?.split(',').pop()?.trim();
            const dateRange = subheadings.find(text => /\d{1,2}\/\d{1,2}\/\d{4}|hasta|to/.test(text));

            const itemHtml = (item.innerHTML || '').toLowerCase()
                .normalize('NFD').replace(/[\u0300-\u036f]/g, '') // remove accents
                .replace(/-/g, '') // remove hyphens so on-line becomes online
                .replace(/\s+/g, ' '); // normalize spaces
            
            const hasOnlineEntry = itemHtml.includes('online entry') || 
                                   itemHtml.includes('inscricao online') || 
                                   itemHtml.includes('inscripcion online') || 
                                   itemHtml.includes('entrada online');

            return [{
                cosatId,
                name,
                url: tournamentUrl.href,
                organization: locationParts[0],
                location,
                country,
                dateRange,
                hasOnlineEntry
            }];
        });
    });
}

async function scrapeTournamentDetails(page: Page, tournament: TournamentListItem): Promise<TournamentDetails> {
    await page.goto(`${BASE_URL}/tournament/${tournament.cosatId}`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);
    await page.waitForSelector('.module, .tournament-meta, table, dl', { timeout: 15000 });

    const rawData = await page.evaluate(() => {
        const clean = (value?: string | null) => (value || '').trim().replace(/\s+/g, ' ');
        const normalize = (value: string) => clean(value)
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase();
        
        const findModuleText = (title: string) => {
            const module = Array.from(document.querySelectorAll('.module')).find(item => (
                clean(item.querySelector('.module__title')?.textContent) === title
            ));

            return clean(module?.textContent).replace(title, '').trim();
        };

        const extractTimelineDates = () => {
            const dates: Record<string, string> = {};
            const assignIfMatches = (label: string, value: string) => {
                const normLabel = normalize(label);
                if (/entry\s+opens?|inscricoes?\s+abrem|inscricao\s+inicio|inscripciones\s+comienzan/i.test(normLabel)) dates.entry_opens = value;
                else if (/closing\s+deadline|cierre\s+de\s+inscripciones?|prazo\s+de\s+inscricao|inscricao\s+fim/i.test(normLabel)) dates.closing_deadline = value;
                else if (/withdrawal\s+deadline|limite\s+de\s+retirada|cierre\s+de\s+retiros?/i.test(normLabel)) dates.withdrawal_deadline = value;
                else if (/start\s+tournament|inicio\s+do\s+torneio|inicio\s+del\s+torneo/i.test(normLabel)) dates.start_tournament = value;
                else if (/end\s+of\s+tournament|fim\s+do\s+torneio|final\s+del\s+torneo/i.test(normLabel)) dates.end_of_tournament = value;
            };

            document.querySelectorAll('tr').forEach(row => {
                const cells = Array.from(row.querySelectorAll('th, td'));
                if (cells.length >= 2) {
                    assignIfMatches(clean(cells[0].textContent), clean(cells.slice(1).map(c => clean(c.textContent)).join(' ')));
                }
            });

            document.querySelectorAll('dt').forEach(term => {
                const details: string[] = [];
                let next = term.nextElementSibling;
                while (next && next.tagName.toLowerCase() !== 'dt') {
                    if (next.tagName.toLowerCase() === 'dd') details.push(clean(next.textContent));
                    next = next.nextElementSibling;
                }
                assignIfMatches(clean(term.textContent), details.join(' '));
            });

            const timelineRegex = /^(Entries?\s+open|Entry\s+start|Inscripciones\s+comienzan(?:[\s\S]*?en)?|Inscricoes?\s+abrem|Inscri\S*\s+inicio|Closing\s+deadline|Fecha\s+de\s+cierre\s+de\s+inscripciones?|Cierre\s+de\s+inscripciones?|Prazo\s+de\s+inscri\S*|Inscri\S*\s+fim|Withdrawal\s+deadline|Fecha\s+de\s+cierre\s+de\s+retiros?|Limite\s+de\s+retirada|Cierre\s+de\s+retiros?|Start\s+tournament|Inicio\s+do\s+torneio|Inicio\s+del\s+torneo|End\s+of\s+tournament|Fim\s+do\s+torneio|Final\s+del\s+torneo)\s*:?\s*(.+)$/i;

            document.querySelectorAll('li, p, div.media__content, .list__item').forEach(el => {
                const text = clean(el.textContent);
                const match = text.match(timelineRegex);
                if (match) {
                    assignIfMatches(match[1], match[2]);
                }
            });

            document.querySelectorAll('.module, .tournament-meta, aside, section').forEach(section => {
                const lines = clean(section.textContent).split(/(?=Entries?\s+open|Inscripciones\s+comienzan|Fecha\s+de\s+cierre|Cierre\s+de|Inicio\s+del\s+torneo|Final\s+del\s+torneo|Start\s+tournament|End\s+of)/i);
                lines.forEach(line => {
                    const match = line.match(timelineRegex);
                    if (match) {
                        assignIfMatches(match[1], match[2]);
                    }
                });
            });

            return dates;
        };

        const metaTexts = Array.from(document.querySelectorAll('.tournament-meta__info-block')).map(item => clean(item.textContent));
        const dateRange = Array.from(document.querySelectorAll('.is-started, .is-finished'))
            .map(item => clean(item.textContent))
            .filter(Boolean)
            .join(' | ') || undefined;
        
        let rawLocation = findModuleText('Lugar') || undefined;
        let organization = findModuleText('Organización') || undefined;

        // Email filtering
        const emailRegex = /([a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z0-9_-]+)/gi;
        if (rawLocation && emailRegex.test(rawLocation)) {
            rawLocation = undefined;
        }
        
        let country = rawLocation?.split(/\s+/).pop();
        const rawDates = extractTimelineDates();

        return {
            organization,
            location: rawLocation,
            country,
            dateRange,
            rawDates,
            categoriesCount: Number(metaTexts.find(text => text.startsWith('Categorías'))?.replace(/\D/g, '')) || undefined,
            entriesCount: Number(metaTexts.find(text => text.startsWith('Inscripciones'))?.replace(/\D/g, '')) || undefined
        };
    });

    const parseCosatDate = (text?: string, referenceYear?: number): { isoDate?: string, tz?: string } => {
        if (!text) return {};
        const cleanText = text.trim().toLowerCase();
        
        const monthMap: Record<string, number> = {
            'jan': 1, 'feb': 2, 'fev': 2, 'mar': 3, 'apr': 4, 'abr': 4, 
            'may': 5, 'mai': 5, 'jun': 6, 'jul': 7, 'aug': 8, 'ago': 8, 
            'sep': 9, 'set': 9, 'oct': 10, 'out': 10, 'nov': 11, 'dec': 12, 'dez': 12, 'dic': 12
        };

        const regex = /(\d{1,2})\s+de\s+([a-z]{3})(?:[a-z]*)\.?\s*(?:(\d{1,2}:\d{2}))?\s*(?:\(GMT\s*([+-]\d{2}:\d{2})\))?/i;
        const match = cleanText.match(regex);

        if (!match) return {};

        const day = parseInt(match[1], 10);
        const monthStr = match[2];
        const time = match[3] || '00:00';
        const tz = match[4];
        
        const month = monthMap[monthStr];
        if (!month) return {};

        const year = referenceYear || new Date().getFullYear();
        const paddedMonth = month.toString().padStart(2, '0');
        const paddedDay = day.toString().padStart(2, '0');
        
        const tzSuffix = tz ? tz : '';
        const isoDate = `${year}-${paddedMonth}-${paddedDay}T${time}:00${tzSuffix}`;
        
        return { isoDate, tz };
    };

    let yearHint = new Date().getFullYear();
    const dateRange = rawData.dateRange || tournament.dateRange || '';
    const yearMatch = dateRange.match(/\b(20\d{2})\b/);
    if (yearMatch) {
        yearHint = parseInt(yearMatch[1], 10);
    } else {
        const urlYearMatch = tournament.url.match(/\b(20\d{2})\b/);
        if (urlYearMatch) yearHint = parseInt(urlYearMatch[1], 10);
    }

    const { isoDate: registration_open_at, tz: tzOpen } = parseCosatDate(rawData.rawDates.entry_opens, yearHint);
    const { isoDate: registration_close_at, tz: tzClose } = parseCosatDate(rawData.rawDates.closing_deadline, yearHint);
    const { isoDate: withdrawal_deadline_at, tz: tzWithdrawal } = parseCosatDate(rawData.rawDates.withdrawal_deadline, yearHint);
    const { isoDate: tournament_start_at } = parseCosatDate(rawData.rawDates.start_tournament, yearHint);
    const { isoDate: tournament_end_at } = parseCosatDate(rawData.rawDates.end_of_tournament, yearHint);

    let timezone = tzOpen || tzClose || tzWithdrawal;
    if (timezone) {
        timezone = `GMT${timezone}`;
    }

    // Set default location if it was an email or empty
    const finalLocation = rawData.location || tournament.location || 'Local a confirmar';

    return {
        organization: rawData.organization,
        location: finalLocation,
        country: rawData.country,
        dateRange: rawData.dateRange,
        registration_open_at,
        registration_close_at,
        withdrawal_deadline_at,
        tournament_start_at,
        tournament_end_at,
        timezone,
        source_dates_raw: Object.keys(rawData.rawDates).length > 0 ? rawData.rawDates : undefined,
        categoriesCount: rawData.categoriesCount,
        entriesCount: rawData.entriesCount
    };
}

async function scrapeTournamentEvents(page: Page, tournamentId: string): Promise<TournamentEvent[]> {
    await page.goto(`${BASE_URL}/sport/events.aspx?id=${tournamentId}`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1000);

    return page.$$eval('table.admintournamentevents tr', rows => {
        return rows.slice(1).map(row => {
            const cells = Array.from(row.querySelectorAll('td'));
            const link = cells[0]?.querySelector<HTMLAnchorElement>('a');
            const href = link?.getAttribute('href') || '';
            const eventUrl = href ? new URL(href, window.location.origin) : undefined;

            return {
                eventId: eventUrl?.searchParams.get('event') || undefined,
                name: cells[0]?.textContent?.trim().replace(/\s+/g, ' ') || '',
                draws: Number(cells[1]?.textContent?.replace(/\D/g, '')) || undefined,
                entries: Number(cells[2]?.textContent?.replace(/\D/g, '')) || undefined
            };
        }).filter(event => event.name);
    });
}

async function scrapeTournamentPlayers(page: Page, tournament: TournamentListItem): Promise<TournamentPlayer[]> {
    await page.goto(`${BASE_URL}/sport/players.aspx?id=${tournament.cosatId}`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);

    return page.$$eval('.js-alphabet-list-item', (items, payload) => {
        return items.flatMap(item => {
            const link = item.querySelector<HTMLAnchorElement>('a[href*="player="]');
            if (!link) return [];

            const href = link.getAttribute('href') || '';
            const playerUrl = new URL(href, window.location.origin);
            const name = link.textContent?.trim().replace(/\s+/g, ' ') || '';
            if (!name) return [];

            return [{
                name,
                country: item.querySelector('.media__subheading .nav-link__value')?.textContent?.trim().replace(/\s+/g, ' ') || undefined,
                countryCode: item.querySelector<HTMLImageElement>('img.icon-lang')?.alt || undefined,
                tournamentId: payload.tournamentId,
                tournamentName: payload.tournamentName,
                tournamentPlayerId: playerUrl.searchParams.get('player') || undefined
            }];
        });
    }, { tournamentId: tournament.cosatId, tournamentName: tournament.name });
}

async function scrapeRankingOverview(page: Page) {
    await page.goto(`${BASE_URL}/ranking`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    await page.waitForSelector('table.ruler', { timeout: 15000 });

    return page.evaluate(() => {
        const clean = (value?: string | null) => (value || '').trim().replace(/\s+/g, ' ');
        const sourceUrl = window.location.href;
        const rankingId = new URL(sourceUrl).searchParams.get('rid') || undefined;
        const rankingDate = clean(document.querySelector('.rankingdate')?.textContent) || undefined;
        const updatedText = clean(document.querySelector('.subtitle')?.textContent) || undefined;
        const categoriesById = new Map<string, RankingCategory>();

        document.querySelectorAll('table.ruler tr').forEach(row => {
            const categoryLink = row.querySelector<HTMLAnchorElement>('th:first-child a[href*="category="]');
            const name = clean(categoryLink?.textContent);
            const href = categoryLink?.getAttribute('href') || '';
            if (!name || !href || name.toLowerCase() === 'más') return;

            const url = new URL(href, window.location.href);
            const categoryId = url.searchParams.get('category') || name;
            categoriesById.set(categoryId, { name, url: url.href });
        });

        const categories = Array.from(categoriesById.values());

        return { rankingId, rankingDate, updatedText, sourceUrl, categories };
    });
}

async function scrapeRankingCategoryPage(page: Page, category: RankingCategory): Promise<{ entries: RankingEntryData[]; totalPages: number }> {
    await page.waitForSelector('table.ruler', { timeout: 15000 });

    return page.evaluate((categoryName) => {
        const clean = (value?: string | null) => (value || '').trim().replace(/\s+/g, ' ');
        const entries: RankingEntryData[] = [];

        document.querySelectorAll('table.ruler tr').forEach(row => {
            const cells = Array.from(row.querySelectorAll('td'));

            if (cells.length < 10) return;

            const playerLink = row.querySelector<HTMLAnchorElement>('a[href*="player="]');
            const profileLink = row.querySelector<HTMLAnchorElement>('a[href*="/player-profile/"]');
            const playerHref = playerLink?.getAttribute('href') || '';
            const playerUrl = playerHref ? new URL(playerHref, window.location.href) : undefined;
            const rank = Number(clean(cells[0]?.textContent));

            if (!playerLink || !rank) return;

            entries.push({
                category: categoryName,
                rank,
                playerName: clean(playerLink.textContent),
                playerId: playerUrl?.searchParams.get('player') || undefined,
                profileId: profileLink?.getAttribute('href')?.split('/').filter(Boolean).pop(),
                dob: clean(cells[5]?.textContent) || undefined,
                singlesPoints: clean(cells[6]?.textContent) || undefined,
                doublesPoints: clean(cells[7]?.textContent) || undefined,
                bonusPoints: clean(cells[8]?.textContent) || undefined,
                totalPoints: clean(cells[9]?.textContent) || undefined,
                country: clean(cells[10]?.textContent) || undefined
            });
        });

        const pagerText = clean(document.querySelector('td.noruler')?.textContent);
        const totalPages = Number(pagerText.match(/Página\s+\d+\s+de\s+(\d+)/i)?.[1]) || 1;

        return { entries, totalPages };
    }, category.name);
}

async function scrapeRanking(page: Page): Promise<RankingData> {
    const overview = await scrapeRankingOverview(page);
    const entries: RankingEntryData[] = [];

    for (const category of overview.categories) {
        const firstPageUrl = new URL(category.url);
        firstPageUrl.searchParams.set('ps', '100');
        firstPageUrl.searchParams.set('p', '1');

        console.log(`Extraindo ranking: ${category.name}`);
        await page.goto(firstPageUrl.href, { waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(1200);

        const firstPage = await scrapeRankingCategoryPage(page, category);
        entries.push(...firstPage.entries);

        for (let pageNumber = 2; pageNumber <= firstPage.totalPages; pageNumber++) {
            const pageUrl = new URL(firstPageUrl.href);
            pageUrl.searchParams.set('p', String(pageNumber));

            await page.goto(pageUrl.href, { waitUntil: 'domcontentloaded' });
            await page.waitForTimeout(800);

            const rankingPage = await scrapeRankingCategoryPage(page, category);
            entries.push(...rankingPage.entries);
        }
    }

    return {
        rankingId: overview.rankingId,
        rankingDate: overview.rankingDate,
        updatedText: overview.updatedText,
        sourceUrl: overview.sourceUrl,
        entries
    };
}

export async function startRankingScraping() {
    console.log('Abrindo navegador para ranking...');
    const browser = await chromium.launch({
        headless,
        timeout: 30000,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage'
        ]
    });

    const context = await browser.newContext({
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    });

    const page = await context.newPage();
    page.setDefaultNavigationTimeout(20000);
    page.setDefaultTimeout(15000);

    try {
        console.log('Buscando ranking completo...');
        const ranking = await scrapeRanking(page);

        for (const entry of ranking.entries) {
            await RankingEntry.findOneAndUpdate(
                { rankingId: ranking.rankingId, category: entry.category, playerId: entry.playerId },
                {
                    ...entry,
                    rankingId: ranking.rankingId,
                    rankingDate: ranking.rankingDate,
                    updatedText: ranking.updatedText,
                    sourceUrl: ranking.sourceUrl,
                    lastUpdated: new Date()
                },
                { upsert: true, new: true }
            );

            await Player.findOneAndUpdate(
                entry.profileId ? { profileId: entry.profileId } : { rankingPlayerId: entry.playerId, rankingCategory: entry.category },
                {
                    name: entry.playerName,
                    country: entry.country,
                    rankingPlayerId: entry.playerId,
                    profileId: entry.profileId,
                    dob: entry.dob,
                    rankingCategory: entry.category,
                    lastUpdated: new Date()
                },
                { upsert: true, new: true }
            );
        }

        console.log(`Ranking completo: ${ranking.entries.length} registros extraidos.`);
    } catch (error) {
        console.error('Falha na extracao do ranking:', error);
    } finally {
        await browser.close();
    }
}

export async function startScraping() {
    console.log('Abrindo navegador...');
    const browser = await chromium.launch({
        headless,
        timeout: 30000,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage'
        ]
    });

    try {
        console.log('Buscando lista de torneios...');
        const tournaments = await withScrapingPage(browser, page => scrapeTournamentList(page));
        console.log(`Foram encontrados ${tournaments.length} torneios.`);

        for (const tournament of tournaments) {
            console.log(`Extraindo torneio: ${tournament.name}`);
            await withRetry(`torneio ${tournament.name}`, async () => {
                await withScrapingPage(browser, async page => {
                    const details = await scrapeTournamentDetails(page, tournament);
                    const events = await scrapeTournamentEvents(page, tournament.cosatId);
                    const players = await scrapeTournamentPlayers(page, tournament);

                    // Derive city/state from location
                    const rawLocation = details.location || tournament.location || '';
                    const finalLocation = isValidLocation(rawLocation) ? rawLocation : '';
                    const { city, state } = parseLocationBR(finalLocation);

                    // Infer modality
                    const modality = inferModality(
                        tournament.name,
                        details.organization || tournament.organization || ''
                    );

                    // Validate data quality
                    const validationErrors = validateTournament({
                        cosatId: tournament.cosatId,
                        name: tournament.name,
                        location: finalLocation,
                        state,
                        tournament_start_at: details.tournament_start_at,
                        tournament_end_at: details.tournament_end_at,
                    });

                    if (validationErrors.length > 0) {
                        console.warn(`[VALIDAÇÃO] ${tournament.name} (${tournament.cosatId}): ${validationErrors.join(', ')}`);
                    }

                    await Tournament.findOneAndUpdate(
                        { cosatId: tournament.cosatId },
                        {
                            $set: {
                                ...tournament,
                                ...details,
                                location: finalLocation || tournament.location,
                                city,
                                state,
                                modality,
                                events,
                                playersCount: players.length,
                                validation_errors: validationErrors,
                                normalized_at: new Date(),
                                lastUpdated: new Date()
                            },
                            $unset: {
                                'Inscrição_Inicio': 1,
                                'Inscrição_Fim': 1
                            }
                        },
                        { upsert: true, new: true, strict: false }
                    );

                    for (const player of players) {
                        await Player.findOneAndUpdate(
                            { tournamentId: player.tournamentId, tournamentPlayerId: player.tournamentPlayerId },
                            { ...player, lastUpdated: new Date() },
                            { upsert: true, new: true }
                        );
                    }
                });
            }).catch(error => {
                console.error(`Torneio ignorado apos falhas: ${tournament.name}`, error);
            });
        }

        console.log('Buscando ranking geral...');
        const ranking = await withRetry('ranking geral', () => (
            withScrapingPage(browser, page => scrapeRanking(page))
        ));

        for (const entry of ranking.entries) {
            await RankingEntry.findOneAndUpdate(
                { rankingId: ranking.rankingId, category: entry.category, playerId: entry.playerId },
                {
                    ...entry,
                    rankingId: ranking.rankingId,
                    rankingDate: ranking.rankingDate,
                    updatedText: ranking.updatedText,
                    sourceUrl: ranking.sourceUrl,
                    lastUpdated: new Date()
                },
                { upsert: true, new: true }
            );

            await Player.findOneAndUpdate(
                entry.profileId ? { profileId: entry.profileId } : { rankingPlayerId: entry.playerId, rankingCategory: entry.category },
                {
                    name: entry.playerName,
                    country: entry.country,
                    rankingPlayerId: entry.playerId,
                    profileId: entry.profileId,
                    dob: entry.dob,
                    rankingCategory: entry.category,
                    lastUpdated: new Date()
                },
                { upsert: true, new: true }
            );
        }

        console.log(`Ranking: ${ranking.entries.length} registros extraidos.`);
        console.log('Extracao completa finalizada com sucesso.');
    } catch (error) {
        console.error('Falha na extracao:', error);
        throw error;
    } finally {
        await browser.close();
    }
}
