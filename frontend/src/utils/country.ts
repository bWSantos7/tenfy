// Country helpers for international tournaments (UTR / ITF / COSAT).
//
// Sources use different 3-letter code systems:
//   - UTR / COSAT → ISO 3166-1 alpha-3 (BRA, ARG, CHL...)
//   - ITF         → IOC codes (LAT, TPE, BRN, GER...) which differ from ISO for
//                   ~30 countries.
// We map both variants to an ISO alpha-2 (for the flag) plus a pt-BR name.

// 3-letter code (ISO alpha-3 AND IOC variants) → [ISO alpha-2, nome pt-BR]
const COUNTRY_BY_CODE3: Record<string, [string, string]> = {
  // ── América do Sul (COSAT) ──
  ARG: ['AR', 'Argentina'], BOL: ['BO', 'Bolívia'], BRA: ['BR', 'Brasil'],
  CHL: ['CL', 'Chile'], CHI: ['CL', 'Chile'], COL: ['CO', 'Colômbia'],
  ECU: ['EC', 'Equador'], PRY: ['PY', 'Paraguai'], PAR: ['PY', 'Paraguai'],
  PER: ['PE', 'Peru'], URY: ['UY', 'Uruguai'], URU: ['UY', 'Uruguai'],
  VEN: ['VE', 'Venezuela'], GUY: ['GY', 'Guiana'], SUR: ['SR', 'Suriname'],
  // ── Américas ──
  USA: ['US', 'Estados Unidos'], CAN: ['CA', 'Canadá'], MEX: ['MX', 'México'],
  CRC: ['CR', 'Costa Rica'], CRI: ['CR', 'Costa Rica'], DOM: ['DO', 'Rep. Dominicana'],
  PUR: ['PR', 'Porto Rico'], PRI: ['PR', 'Porto Rico'], GUA: ['GT', 'Guatemala'],
  ESA: ['SV', 'El Salvador'], PAN: ['PA', 'Panamá'], JAM: ['JM', 'Jamaica'],
  BAR: ['BB', 'Barbados'], TTO: ['TT', 'Trinidad e Tobago'], CUB: ['CU', 'Cuba'],
  // ── Europa ──
  GBR: ['GB', 'Reino Unido'], FRA: ['FR', 'França'], ESP: ['ES', 'Espanha'],
  ITA: ['IT', 'Itália'], GER: ['DE', 'Alemanha'], DEU: ['DE', 'Alemanha'],
  SUI: ['CH', 'Suíça'], CHE: ['CH', 'Suíça'], AUT: ['AT', 'Áustria'],
  NED: ['NL', 'Holanda'], NLD: ['NL', 'Holanda'], BEL: ['BE', 'Bélgica'],
  POR: ['PT', 'Portugal'], PRT: ['PT', 'Portugal'], SWE: ['SE', 'Suécia'],
  NOR: ['NO', 'Noruega'], DEN: ['DK', 'Dinamarca'], DNK: ['DK', 'Dinamarca'],
  FIN: ['FI', 'Finlândia'], IRL: ['IE', 'Irlanda'], POL: ['PL', 'Polônia'],
  CZE: ['CZ', 'Tchéquia'], SVK: ['SK', 'Eslováquia'], SLO: ['SI', 'Eslovênia'],
  SVN: ['SI', 'Eslovênia'], HUN: ['HU', 'Hungria'], ROU: ['RO', 'Romênia'],
  BUL: ['BG', 'Bulgária'], BGR: ['BG', 'Bulgária'], GRE: ['GR', 'Grécia'],
  GRC: ['GR', 'Grécia'], CRO: ['HR', 'Croácia'], HRV: ['HR', 'Croácia'],
  SRB: ['RS', 'Sérvia'], UKR: ['UA', 'Ucrânia'], RUS: ['RU', 'Rússia'],
  TUR: ['TR', 'Turquia'], LAT: ['LV', 'Letônia'], LVA: ['LV', 'Letônia'],
  LTU: ['LT', 'Lituânia'], EST: ['EE', 'Estônia'], GEO: ['GE', 'Geórgia'],
  ARM: ['AM', 'Armênia'], AZE: ['AZ', 'Azerbaijão'], CYP: ['CY', 'Chipre'],
  LUX: ['LU', 'Luxemburgo'], ISL: ['IS', 'Islândia'], BLR: ['BY', 'Belarus'],
  MDA: ['MD', 'Moldávia'], MKD: ['MK', 'Macedônia do Norte'], BIH: ['BA', 'Bósnia'],
  MNE: ['ME', 'Montenegro'], MLT: ['MT', 'Malta'], MON: ['MC', 'Mônaco'],
  // ── Ásia / Oceania ──
  AUS: ['AU', 'Austrália'], NZL: ['NZ', 'Nova Zelândia'], JPN: ['JP', 'Japão'],
  CHN: ['CN', 'China'], KOR: ['KR', 'Coreia do Sul'], TPE: ['TW', 'Taipé Chinesa'],
  TWN: ['TW', 'Taiwan'], IND: ['IN', 'Índia'], THA: ['TH', 'Tailândia'],
  INA: ['ID', 'Indonésia'], IDN: ['ID', 'Indonésia'], MAS: ['MY', 'Malásia'],
  MYS: ['MY', 'Malásia'], SGP: ['SG', 'Singapura'], HKG: ['HK', 'Hong Kong'],
  PHI: ['PH', 'Filipinas'], PHL: ['PH', 'Filipinas'], VIE: ['VN', 'Vietnã'],
  VNM: ['VN', 'Vietnã'], KAZ: ['KZ', 'Cazaquistão'], UZB: ['UZ', 'Uzbequistão'],
  ISR: ['IL', 'Israel'], BRN: ['BH', 'Bahrein'], BHR: ['BH', 'Bahrein'],
  UAE: ['AE', 'Emirados Árabes'], ARE: ['AE', 'Emirados Árabes'], QAT: ['QA', 'Catar'],
  KSA: ['SA', 'Arábia Saudita'], SAU: ['SA', 'Arábia Saudita'], JOR: ['JO', 'Jordânia'],
  LIB: ['LB', 'Líbano'], PAK: ['PK', 'Paquistão'], SRI: ['LK', 'Sri Lanka'],
  // ── África ──
  RSA: ['ZA', 'África do Sul'], ZAF: ['ZA', 'África do Sul'], EGY: ['EG', 'Egito'],
  MAR: ['MA', 'Marrocos'], TUN: ['TN', 'Tunísia'], ALG: ['DZ', 'Argélia'],
  NGR: ['NG', 'Nigéria'], KEN: ['KE', 'Quênia'],
};

export interface CountryInfo {
  code2: string;   // ISO alpha-2 (lowercase-friendly), e.g. 'BR'
  name: string;    // pt-BR display name (or the raw code as fallback)
}

/** Resolve a 2- or 3-letter country code to flag/name info. Null when unknown. */
export function resolveCountry(code?: string | null): CountryInfo | null {
  if (!code) return null;
  const c = code.trim().toUpperCase();
  if (!c) return null;
  if (c.length === 3 && COUNTRY_BY_CODE3[c]) {
    const [code2, name] = COUNTRY_BY_CODE3[c];
    return { code2, name };
  }
  if (c.length === 2) {
    // Already alpha-2: find a pt-BR name if we have one, else use the code.
    const match = Object.values(COUNTRY_BY_CODE3).find(([a2]) => a2 === c);
    return { code2: c, name: match ? match[1] : c };
  }
  return null;
}

/** Emoji flag from an ISO alpha-2 code (works on web; not all Android render it). */
export function flagEmoji(code2: string): string {
  const c = (code2 || '').trim().toUpperCase();
  if (c.length !== 2) return '';
  return c.replace(/./g, (ch) => String.fromCodePoint(127397 + ch.charCodeAt(0)));
}

/**
 * Country display for an edition (international sources). Prefers an explicit
 * country name from the venue, falling back to a name derived from the code.
 * Returns null when there is no usable country info.
 */
export function editionCountry(opts: {
  venue_country?: string | null;
  venue_country_code?: string | null;
}): { code2: string; name: string; flag: string } | null {
  const info = resolveCountry(opts.venue_country_code);
  if (!info) {
    // No mappable code: still show an explicit country name if present.
    const name = (opts.venue_country || '').trim();
    return name ? { code2: '', name, flag: '' } : null;
  }
  const name = (opts.venue_country || '').trim() || info.name;
  return { code2: info.code2, name, flag: flagEmoji(info.code2) };
}
