import { format, formatDistanceToNow, parseISO } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import { TournamentChangeEvent, TournamentStatus } from '../types';

/** Basic e-mail format check (mirrors the backend EmailField validation). */
export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test((email || '').trim());
}

/** Idade calculada a partir da data (preferida) ou do ano de nascimento. */
export function calculateAge(birthDate?: string | null, birthYear?: number | null): number | null {
  if (birthDate) {
    const d = new Date(birthDate);
    if (!Number.isNaN(d.getTime())) {
      const now = new Date();
      let age = now.getFullYear() - d.getFullYear();
      const m = now.getMonth() - d.getMonth();
      if (m < 0 || (m === 0 && now.getDate() < d.getDate())) age--;
      return age;
    }
  }
  if (birthYear) return new Date().getFullYear() - birthYear;
  return null;
}

export function fmtRadius(km: number | null | undefined): string {
  if (km == null) return '100 km';
  return km >= 1000 ? 'Todo o Brasil' : `${km} km`;
}

export function fmtDate(iso: string | null | undefined, pattern = "dd 'de' MMMM") {
  if (!iso) return '—';
  try {
    return format(parseISO(iso), pattern, { locale: ptBR });
  } catch {
    return '—';
  }
}

export function fmtDateShort(iso: string | null | undefined) {
  if (!iso) return '—';
  try {
    return format(parseISO(iso), 'dd/MM/yyyy', { locale: ptBR });
  } catch {
    return '—';
  }
}

export function fmtDateTime(iso: string | null | undefined) {
  if (!iso) return '—';
  try {
    return format(parseISO(iso), "dd/MM/yyyy 'às' HH:mm", { locale: ptBR });
  } catch {
    return '—';
  }
}

/**
 * Format a datetime ISO string as "dd/MM/yyyy" (date only) when the time
 * component is midnight (00:00), or as "dd/MM/yyyy 'às' HH:mm" when there
 * is a real time. Prevents showing "00:00" for date-only sources (e.g. COSAT).
 */
export function fmtDateMaybeTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const d = parseISO(iso);
    const hasMeaningfulTime = d.getHours() !== 0 || d.getMinutes() !== 0;
    return hasMeaningfulTime
      ? format(d, "dd/MM/yyyy 'às' HH:mm", { locale: ptBR })
      : format(d, 'dd/MM/yyyy', { locale: ptBR });
  } catch {
    return '—';
  }
}

export function fmtDateRange(start: string | null, end: string | null): string {
  if (!start && !end) return 'A definir';
  if (start && !end) return fmtDate(start);
  if (!start && end) return fmtDate(end);
  try {
    const a = parseISO(start!);
    const b = parseISO(end!);
    if (a.getMonth() === b.getMonth() && a.getFullYear() === b.getFullYear()) {
      return `${format(a, 'dd', { locale: ptBR })} – ${format(b, "dd 'de' MMMM", { locale: ptBR })}`;
    }
    return `${format(a, 'dd/MM', { locale: ptBR })} – ${format(b, 'dd/MM/yyyy', { locale: ptBR })}`;
  } catch {
    return '—';
  }
}

export function fmtRelative(iso: string | null) {
  if (!iso) return '—';
  try {
    return formatDistanceToNow(parseISO(iso), { addSuffix: true, locale: ptBR });
  } catch {
    return '—';
  }
}

export function statusColorClass(status: TournamentStatus): string {
  switch (status) {
    case 'open': return 'text-status-open';
    case 'closing_soon': return 'text-status-closing';
    case 'closed': return 'text-status-closed';
    case 'draws_published': return 'text-status-drawn';
    case 'in_progress': return 'text-status-progress';
    case 'finished': return 'text-status-finished';
    case 'canceled': return 'text-status-canceled';
    default: return 'text-text-muted';
  }
}

export function statusBgClass(status: TournamentStatus): string {
  switch (status) {
    case 'open': return 'bg-status-open/15 text-status-open border-status-open/30';
    case 'closing_soon': return 'bg-status-closing/15 text-status-closing border-status-closing/30';
    case 'closed': return 'bg-status-closed/15 text-status-closed border-status-closed/30';
    case 'draws_published': return 'bg-status-drawn/15 text-status-drawn border-status-drawn/30';
    case 'in_progress': return 'bg-status-progress/15 text-status-progress border-status-progress/30';
    case 'finished': return 'bg-status-finished/15 text-status-finished border-status-finished/30';
    case 'canceled': return 'bg-status-canceled/15 text-status-canceled border-status-canceled/30';
    default: return 'bg-bg-elevated text-text-muted border-border-subtle';
  }
}

export const ROLE_LABELS: Record<string, string> = {
  player: 'Jogador(a)',
  coach: 'Treinador(a)',
  parent: 'Responsável',
  admin: 'Administrador(a)',
};

// Níveis padronizados conforme CBT (Task 12) — por faixa etária.
export const LEVEL_LABELS: Record<string, string> = {
  kids: 'Crianças',
  youth: 'Juvenil',
  pro: 'Profissional',
  seniors: 'Idosos',
};


export const GENDER_LABELS: Record<string, string> = {
  M: 'Masculino',
  F: 'Feminino',
};

export const STATUS_LABELS: Record<TournamentStatus, string> = {
  unknown: 'Desconhecido',
  announced: 'Anunciado',
  open: 'Inscrições Abertas',
  closing_soon: 'Encerrando inscrições em breve',
  closed: 'Inscrições Encerradas',
  draws_published: 'Chaves Publicadas',
  in_progress: 'Em Andamento',
  finished: 'Finalizado',
  canceled: 'Cancelado',
};

export const SURFACE_LABELS: Record<string, string> = {
  clay: 'Saibro',
  hard: 'Rápida / Sintética',
  grass: 'Grama',
  sand: 'Areia',
  carpet: 'Carpete',
  unknown: 'Não informada',
};

export function fmtBRL(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  const n = typeof value === 'string' ? parseFloat(value) : value;
  if (Number.isNaN(n)) return '—';
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

export const REASON_LABELS: Record<string, string> = {
  age_out_of_range: 'Idade fora da faixa',
  gender_mismatch: 'Gênero não compatível',
  class_too_low: 'Classe abaixo do exigido',
  class_too_high: 'Classe acima do permitido',
  no_birth_year: 'Complete sua data de nascimento',
  no_gender: 'Complete seu gênero no perfil',
  no_class: 'Defina sua classe no perfil',
  no_rule_available: 'Regra oficial indisponível',
  category_not_normalized: 'Categoria não reconhecida pelo motor',
  matches_profile: 'Compatível com seu perfil',
};

export function translateReason(code: string): string {
  return REASON_LABELS[code] || code;
}

const CHANGE_EVENT_LABELS: Record<string, string> = {
  created: 'Torneio adicionado ao Tenfy',
  status_changed: 'Status do torneio atualizado',
  dates_changed: 'Datas do torneio atualizadas',
  deadline_changed: 'Prazo de inscrição atualizado',
  price_changed: 'Valores atualizados',
  venue_changed: 'Local do torneio atualizado',
  categories_changed: 'Categorias atualizadas',
  canceled: 'Torneio cancelado',
  draws_published: 'Chaves publicadas',
  other: 'Informações do torneio atualizadas',
};

const CHANGE_FIELD_LABELS: Record<string, string> = {
  title: 'nome do torneio',
  start_date: 'data de início',
  end_date: 'data de término',
  entry_open_at: 'abertura das inscrições',
  entry_close_at: 'prazo de inscrição',
  status: 'status',
  surface: 'superfície',
  base_price_brl: 'valor da inscrição',
  official_source_url: 'link oficial',
  data_confidence: 'confiabilidade dos dados',
  source_name: 'fonte dos dados',
};

function formatChangeValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return 'não informado';

  if (field === 'status' && typeof value === 'string') {
    return STATUS_LABELS[value as TournamentStatus] || value;
  }

  if (field === 'base_price_brl') {
    return fmtBRL(value as string | number | null | undefined);
  }

  if (field.endsWith('_date') || field.endsWith('_at')) {
    const text = String(value);
    return text.includes('T') ? fmtDateTime(text) : fmtDateShort(text);
  }

  if (typeof value === 'boolean') {
    return value ? 'sim' : 'não';
  }

  return String(value);
}

function humanizeFieldName(field: string): string {
  return field
    .replace(/_id$/, '')
    .replace(/_/g, ' ')
    .replace(/\burl\b/gi, 'link')
    .replace(/\bid\b/gi, 'identificador');
}

export function formatChangeEventTitle(eventType: string): string {
  return CHANGE_EVENT_LABELS[eventType] || 'Informações do torneio atualizadas';
}

export function formatChangeEventDetails(event: TournamentChangeEvent): string[] {
  if (event.event_type === 'created') {
    return ['Esse torneio passou a aparecer no Tenfy.'];
  }

  const entries = Object.entries(event.field_changes || {});
  if (entries.length === 0) {
    return [];
  }

  return entries.map(([field, diff]) => {
    const label = CHANGE_FIELD_LABELS[field] || humanizeFieldName(field);
    if (diff && typeof diff === 'object' && !Array.isArray(diff)) {
      const typedDiff = diff as { old?: unknown; new?: unknown };
      const oldValue = formatChangeValue(field, typedDiff.old);
      const newValue = formatChangeValue(field, typedDiff.new);
      return `${label}: de ${oldValue} para ${newValue}.`;
    }
    return `${label} atualizado.`;
  });
}
