import React, { useCallback, useEffect, useState } from 'react';
import { Loader2, Plus, RefreshCcw, Tag, X, Check, Ban, Wallet } from 'lucide-react';
import toast from 'react-hot-toast';
import { extractApiError } from '../../services/api';
import {
  Partner, Coupon, CommissionRule, Commission, Payout, CommissionSummaryRow,
  PartnerType, DiscountType, PlanScope, CouponStatus, BaseAmountType, CommissionStatus,
  listPartners, createPartner, updatePartner,
  listCoupons, createCoupon, updateCoupon,
  listCommissionRules, createCommissionRule, updateCommissionRule,
  listCommissions, updateCommissionStatus, commissionsSummary,
  listPayouts, createPayout,
} from '../../services/referrals';

// ─── Labels ──────────────────────────────────────────────────────────────────

const PARTNER_TYPE_LABELS: Record<PartnerType, string> = {
  influencer: 'Influenciador', coach: 'Treinador', academy: 'Academia',
  ambassador: 'Embaixador', other: 'Outro',
};
const COUPON_STATUS_LABELS: Record<CouponStatus, string> = {
  draft: 'Rascunho', active: 'Ativo', inactive: 'Inativo', expired: 'Expirado', exhausted: 'Esgotado',
};
const SCOPE_LABELS: Record<PlanScope, string> = {
  individual: 'Individual', familia: 'Família', both: 'Ambos',
};
const COMMISSION_STATUS_LABELS: Record<CommissionStatus, string> = {
  pending: 'Pendente', approved: 'Aprovada', paid: 'Paga', reversed: 'Revertida', canceled: 'Cancelada',
};
const COMMISSION_STATUS_COLOR: Record<CommissionStatus, string> = {
  pending: 'text-amber-400', approved: 'text-blue-400', paid: 'text-green-400',
  reversed: 'text-red-400', canceled: 'text-gray-400',
};

function brl(v: string | number): string {
  const n = typeof v === 'string' ? parseFloat(v) : v;
  if (Number.isNaN(n)) return String(v);
  return `R$ ${n.toFixed(2).replace('.', ',')}`;
}
function fmtDate(d: string | null): string {
  return d ? new Date(d).toLocaleDateString('pt-BR') : '—';
}

type Sub = 'partners' | 'coupons' | 'rules' | 'commissions' | 'payouts';

const SUBS: [Sub, string][] = [
  ['partners', 'Parceiros'],
  ['coupons', 'Cupons'],
  ['rules', 'Regras'],
  ['commissions', 'Comissões'],
  ['payouts', 'Repasses'],
];

export const ReferralsAdminTab: React.FC = () => {
  const [sub, setSub] = useState<Sub>('partners');
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1.5 text-sm font-semibold">
        <Tag className="w-4 h-4 text-accent-neon" /> Programa de parceiros
      </div>
      <div className="flex gap-1 flex-wrap">
        {SUBS.map(([key, label]) => (
          <button
            key={key}
            onClick={() => setSub(key)}
            className={`px-3 py-1.5 rounded text-xs font-medium border ${
              sub === key
                ? 'border-accent-neon text-accent-neon bg-accent-neon/10'
                : 'border-border-subtle text-text-muted hover:text-text-primary'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {sub === 'partners' && <PartnersSection />}
      {sub === 'coupons' && <CouponsSection />}
      {sub === 'rules' && <RulesSection />}
      {sub === 'commissions' && <CommissionsSection />}
      {sub === 'payouts' && <PayoutsSection />}
    </div>
  );
};

// ─── Helpers de UI ─────────────────────────────────────────────────────────────

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <label className="block text-xs">
    <span className="text-text-muted">{label}</span>
    <div className="mt-0.5">{children}</div>
  </label>
);

const Empty: React.FC<{ text: string }> = ({ text }) => (
  <div className="text-xs text-text-muted text-center py-6">{text}</div>
);

const Spinner: React.FC = () => (
  <div className="flex justify-center py-6"><Loader2 className="w-6 h-6 animate-spin text-text-muted" /></div>
);

// ─── Parceiros ───────────────────────────────────────────────────────────────────

const EMPTY_PARTNER: Partial<Partner> = { name: '', type: 'influencer', email: '', phone: '', status: 'active', payout_method: '', payout_details: '' };

const PartnersSection: React.FC = () => {
  const [items, setItems] = useState<Partner[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<Partial<Partner> | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setItems((await listPartners()).results); }
    catch (e) { toast.error(extractApiError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function save() {
    if (!form?.name?.trim()) { toast.error('Informe o nome.'); return; }
    setSaving(true);
    try {
      if (form.id) await updatePartner(form.id, form);
      else await createPartner(form);
      toast.success('Parceiro salvo.');
      setForm(null);
      await load();
    } catch (e) { toast.error(extractApiError(e)); }
    finally { setSaving(false); }
  }

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <button className="btn-secondary !text-xs" onClick={load}><RefreshCcw className="w-3 h-3 inline mr-1" />Atualizar</button>
        <button className="btn-primary !text-xs" onClick={() => setForm({ ...EMPTY_PARTNER })}><Plus className="w-3 h-3 inline mr-1" />Novo parceiro</button>
      </div>

      {form && (
        <div className="card !p-4 space-y-2">
          <div className="flex justify-between items-center">
            <div className="text-sm font-semibold">{form.id ? 'Editar parceiro' : 'Novo parceiro'}</div>
            <button onClick={() => setForm(null)}><X className="w-4 h-4 text-text-muted" /></button>
          </div>
          <div className="grid sm:grid-cols-2 gap-2">
            <Field label="Nome"><input className="input-base w-full text-sm" value={form.name || ''} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Tipo">
              <select className="input-base w-full text-sm" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value as PartnerType })}>
                {Object.entries(PARTNER_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Field>
            <Field label="E-mail"><input className="input-base w-full text-sm" value={form.email || ''} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Field label="Telefone"><input className="input-base w-full text-sm" value={form.phone || ''} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
            <Field label="Status">
              <select className="input-base w-full text-sm" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as Partner['status'] })}>
                <option value="active">Ativo</option><option value="inactive">Inativo</option>
              </select>
            </Field>
            <Field label="Método de repasse">
              <select className="input-base w-full text-sm" value={form.payout_method} onChange={(e) => setForm({ ...form, payout_method: e.target.value })}>
                <option value="">—</option><option value="pix">Pix</option><option value="bank_transfer">Transferência</option><option value="manual">Manual</option>
              </select>
            </Field>
            <Field label="Dados de repasse (chave Pix)"><input className="input-base w-full text-sm" value={form.payout_details || ''} onChange={(e) => setForm({ ...form, payout_details: e.target.value })} /></Field>
          </div>
          <button className="btn-primary !text-sm w-full" onClick={save} disabled={saving}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin inline" /> : 'Salvar'}
          </button>
        </div>
      )}

      {loading ? <Spinner /> : items.length === 0 ? <Empty text="Nenhum parceiro cadastrado." /> : (
        <div className="space-y-1.5">
          {items.map((p) => (
            <div key={p.id} className="card !p-3 flex justify-between items-center">
              <div>
                <div className="text-sm font-medium">{p.name} <span className="text-[11px] text-text-muted">({PARTNER_TYPE_LABELS[p.type]})</span></div>
                <div className="text-[11px] text-text-muted">{p.email || 'sem e-mail'} · {p.coupons_count} cupom(ns) · <span className={p.status === 'active' ? 'text-green-400' : 'text-gray-400'}>{p.status === 'active' ? 'Ativo' : 'Inativo'}</span></div>
              </div>
              <button className="btn-secondary !text-xs" onClick={() => setForm(p)}>Editar</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ─── Cupons ──────────────────────────────────────────────────────────────────────

const EMPTY_COUPON: Partial<Coupon> = {
  code: '', discount_type: 'percent', discount_value: '10', plan_scope: 'both',
  max_uses_per_customer: 1, status: 'active',
};

const CouponsSection: React.FC = () => {
  const [items, setItems] = useState<Coupon[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<Partial<Coupon> | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [c, p] = await Promise.all([listCoupons(), listPartners({ status: 'active' })]);
      setItems(c.results); setPartners(p.results);
    } catch (e) { toast.error(extractApiError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function save() {
    if (!form?.code?.trim()) { toast.error('Informe o código.'); return; }
    if (!form.partner) { toast.error('Selecione o parceiro.'); return; }
    setSaving(true);
    try {
      if (form.id) await updateCoupon(form.id, form);
      else await createCoupon(form);
      toast.success('Cupom salvo.');
      setForm(null); await load();
    } catch (e) { toast.error(extractApiError(e)); }
    finally { setSaving(false); }
  }

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <button className="btn-secondary !text-xs" onClick={load}><RefreshCcw className="w-3 h-3 inline mr-1" />Atualizar</button>
        <button className="btn-primary !text-xs" onClick={() => setForm({ ...EMPTY_COUPON })} disabled={partners.length === 0}><Plus className="w-3 h-3 inline mr-1" />Novo cupom</button>
      </div>
      {partners.length === 0 && !loading && <div className="text-xs text-amber-400">Cadastre um parceiro ativo antes de criar cupons.</div>}

      {form && (
        <div className="card !p-4 space-y-2">
          <div className="flex justify-between items-center">
            <div className="text-sm font-semibold">{form.id ? 'Editar cupom' : 'Novo cupom'}</div>
            <button onClick={() => setForm(null)}><X className="w-4 h-4 text-text-muted" /></button>
          </div>
          <div className="grid sm:grid-cols-2 gap-2">
            <Field label="Código"><input className="input-base w-full text-sm uppercase" value={form.code || ''} onChange={(e) => setForm({ ...form, code: e.target.value })} /></Field>
            <Field label="Parceiro">
              <select className="input-base w-full text-sm" value={form.partner || ''} onChange={(e) => setForm({ ...form, partner: Number(e.target.value) })}>
                <option value="">Selecione…</option>
                {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </Field>
            <Field label="Tipo de desconto">
              <select className="input-base w-full text-sm" value={form.discount_type} onChange={(e) => setForm({ ...form, discount_type: e.target.value as DiscountType })}>
                <option value="percent">Percentual (%)</option><option value="fixed">Valor fixo (R$)</option>
              </select>
            </Field>
            <Field label="Valor"><input className="input-base w-full text-sm" type="number" step="0.01" value={form.discount_value || ''} onChange={(e) => setForm({ ...form, discount_value: e.target.value })} /></Field>
            <Field label="Planos">
              <select className="input-base w-full text-sm" value={form.plan_scope} onChange={(e) => setForm({ ...form, plan_scope: e.target.value as PlanScope })}>
                <option value="both">Ambos</option><option value="individual">Individual</option><option value="familia">Família</option>
              </select>
            </Field>
            <Field label="Status">
              <select className="input-base w-full text-sm" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as CouponStatus })}>
                {Object.entries(COUPON_STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Field>
            <Field label="Limite total de usos (vazio = ilimitado)"><input className="input-base w-full text-sm" type="number" value={form.max_total_uses ?? ''} onChange={(e) => setForm({ ...form, max_total_uses: e.target.value ? Number(e.target.value) : null })} /></Field>
            <Field label="Usos por cliente"><input className="input-base w-full text-sm" type="number" value={form.max_uses_per_customer ?? ''} onChange={(e) => setForm({ ...form, max_uses_per_customer: e.target.value ? Number(e.target.value) : null })} /></Field>
            <Field label="Início (opcional)"><input className="input-base w-full text-sm" type="date" value={form.starts_at ? form.starts_at.slice(0, 10) : ''} onChange={(e) => setForm({ ...form, starts_at: e.target.value || null })} /></Field>
            <Field label="Expira em (opcional)"><input className="input-base w-full text-sm" type="date" value={form.expires_at ? form.expires_at.slice(0, 10) : ''} onChange={(e) => setForm({ ...form, expires_at: e.target.value || null })} /></Field>
          </div>
          <button className="btn-primary !text-sm w-full" onClick={save} disabled={saving}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin inline" /> : 'Salvar'}
          </button>
        </div>
      )}

      {loading ? <Spinner /> : items.length === 0 ? <Empty text="Nenhum cupom cadastrado." /> : (
        <div className="space-y-1.5">
          {items.map((c) => (
            <div key={c.id} className="card !p-3 flex justify-between items-center">
              <div>
                <div className="text-sm font-medium">{c.code} <span className="text-[11px] text-text-muted">· {c.partner_name}</span></div>
                <div className="text-[11px] text-text-muted">
                  {c.discount_type === 'percent' ? `${c.discount_value}%` : brl(c.discount_value)} · {SCOPE_LABELS[c.plan_scope]} · usos {c.times_used}{c.max_total_uses ? `/${c.max_total_uses}` : ''} · <span className={c.status === 'active' ? 'text-green-400' : 'text-gray-400'}>{COUPON_STATUS_LABELS[c.status]}</span>
                </div>
              </div>
              <button className="btn-secondary !text-xs" onClick={() => setForm(c)}>Editar</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ─── Regras de comissão ──────────────────────────────────────────────────────────

const EMPTY_RULE: Partial<CommissionRule> = {
  commission_type: 'percent', commission_value: '20', rule_scope: 'first_payment',
  base_amount_type: 'net_paid', status: 'active', coupon: null,
};

const RulesSection: React.FC = () => {
  const [items, setItems] = useState<CommissionRule[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [coupons, setCoupons] = useState<Coupon[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<Partial<CommissionRule> | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, p, c] = await Promise.all([listCommissionRules(), listPartners({ status: 'active' }), listCoupons()]);
      setItems(r.results); setPartners(p.results); setCoupons(c.results);
    } catch (e) { toast.error(extractApiError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function save() {
    if (!form?.partner) { toast.error('Selecione o parceiro.'); return; }
    setSaving(true);
    try {
      if (form.id) await updateCommissionRule(form.id, form);
      else await createCommissionRule(form);
      toast.success('Regra salva.');
      setForm(null); await load();
    } catch (e) { toast.error(extractApiError(e)); }
    finally { setSaving(false); }
  }

  const couponsForPartner = form?.partner ? coupons.filter((c) => c.partner === form.partner) : [];

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <button className="btn-secondary !text-xs" onClick={load}><RefreshCcw className="w-3 h-3 inline mr-1" />Atualizar</button>
        <button className="btn-primary !text-xs" onClick={() => setForm({ ...EMPTY_RULE })} disabled={partners.length === 0}><Plus className="w-3 h-3 inline mr-1" />Nova regra</button>
      </div>

      {form && (
        <div className="card !p-4 space-y-2">
          <div className="flex justify-between items-center">
            <div className="text-sm font-semibold">{form.id ? 'Editar regra' : 'Nova regra'}</div>
            <button onClick={() => setForm(null)}><X className="w-4 h-4 text-text-muted" /></button>
          </div>
          <div className="grid sm:grid-cols-2 gap-2">
            <Field label="Parceiro">
              <select className="input-base w-full text-sm" value={form.partner || ''} onChange={(e) => setForm({ ...form, partner: Number(e.target.value), coupon: null })}>
                <option value="">Selecione…</option>
                {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </Field>
            <Field label="Cupom (vazio = regra padrão)">
              <select className="input-base w-full text-sm" value={form.coupon ?? ''} onChange={(e) => setForm({ ...form, coupon: e.target.value ? Number(e.target.value) : null })}>
                <option value="">Padrão do parceiro</option>
                {couponsForPartner.map((c) => <option key={c.id} value={c.id}>{c.code}</option>)}
              </select>
            </Field>
            <Field label="Tipo">
              <select className="input-base w-full text-sm" value={form.commission_type} onChange={(e) => setForm({ ...form, commission_type: e.target.value as DiscountType })}>
                <option value="percent">Percentual (%)</option><option value="fixed">Valor fixo (R$)</option>
              </select>
            </Field>
            <Field label="Valor"><input className="input-base w-full text-sm" type="number" step="0.01" value={form.commission_value || ''} onChange={(e) => setForm({ ...form, commission_value: e.target.value })} /></Field>
            <Field label="Base de cálculo">
              <select className="input-base w-full text-sm" value={form.base_amount_type} onChange={(e) => setForm({ ...form, base_amount_type: e.target.value as BaseAmountType })}>
                <option value="net_paid">Valor líquido pago</option><option value="gross_paid">Valor bruto pago</option>
              </select>
            </Field>
            <Field label="Status">
              <select className="input-base w-full text-sm" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as CommissionRule['status'] })}>
                <option value="active">Ativa</option><option value="inactive">Inativa</option>
              </select>
            </Field>
          </div>
          <button className="btn-primary !text-sm w-full" onClick={save} disabled={saving}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin inline" /> : 'Salvar'}
          </button>
        </div>
      )}

      {loading ? <Spinner /> : items.length === 0 ? <Empty text="Nenhuma regra cadastrada." /> : (
        <div className="space-y-1.5">
          {items.map((r) => (
            <div key={r.id} className="card !p-3 flex justify-between items-center">
              <div>
                <div className="text-sm font-medium">{r.partner_name} <span className="text-[11px] text-text-muted">· {r.coupon_code || 'padrão'}</span></div>
                <div className="text-[11px] text-text-muted">
                  {r.commission_type === 'percent' ? `${r.commission_value}%` : brl(r.commission_value)} · base {r.base_amount_type === 'net_paid' ? 'líquida' : 'bruta'} · <span className={r.status === 'active' ? 'text-green-400' : 'text-gray-400'}>{r.status === 'active' ? 'Ativa' : 'Inativa'}</span>
                </div>
              </div>
              <button className="btn-secondary !text-xs" onClick={() => setForm(r)}>Editar</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ─── Comissões + consolidação + repasse ──────────────────────────────────────────

const CommissionsSection: React.FC = () => {
  const [summary, setSummary] = useState<CommissionSummaryRow[]>([]);
  const [items, setItems] = useState<Commission[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [acting, setActing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, c] = await Promise.all([
        commissionsSummary(),
        listCommissions(statusFilter ? { status: statusFilter } : undefined),
      ]);
      setSummary(s.results); setItems(c.results);
    } catch (e) { toast.error(extractApiError(e)); }
    finally { setLoading(false); }
  }, [statusFilter]);
  useEffect(() => { load(); }, [load]);

  async function changeStatus(id: number, status: CommissionStatus) {
    setActing(true);
    try { await updateCommissionStatus(id, status); toast.success('Comissão atualizada.'); await load(); }
    catch (e) { toast.error(extractApiError(e)); }
    finally { setActing(false); }
  }

  async function payout(partnerId: number, partnerName: string) {
    if (!window.confirm(`Registrar repasse de todas as comissões pendentes/aprovadas de ${partnerName}?`)) return;
    setActing(true);
    try {
      const p = await createPayout({ partner: partnerId, method: 'manual' });
      toast.success(`Repasse de ${brl(p.amount)} registrado.`);
      await load();
    } catch (e) { toast.error(extractApiError(e)); }
    finally { setActing(false); }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <button className="btn-secondary !text-xs" onClick={load}><RefreshCcw className="w-3 h-3 inline mr-1" />Atualizar</button>
        <select className="input-base !text-xs !w-auto !py-1" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Todos os status</option>
          {Object.entries(COMMISSION_STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>

      {/* Consolidação por parceiro */}
      <div className="text-xs font-semibold text-text-muted">Consolidação por parceiro</div>
      {loading ? <Spinner /> : summary.length === 0 ? <Empty text="Sem comissões geradas." /> : (
        <div className="space-y-1.5">
          {summary.map((s) => {
            const payable = parseFloat(s.payable_amount);
            return (
              <div key={s.partner_id} className="card !p-3 flex justify-between items-center">
                <div>
                  <div className="text-sm font-medium">{s.partner_name}</div>
                  <div className="text-[11px] text-text-muted">
                    A repassar <span className="text-accent-neon font-semibold">{brl(s.payable_amount)}</span> · pagas {brl(s.paid_amount)} · revertidas {brl(s.reversed_amount)}
                  </div>
                </div>
                <button
                  className="btn-primary !text-xs disabled:opacity-50"
                  onClick={() => payout(s.partner_id, s.partner_name)}
                  disabled={acting || payable <= 0}
                >
                  <Wallet className="w-3 h-3 inline mr-1" />Repassar
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Lista de lançamentos */}
      <div className="text-xs font-semibold text-text-muted pt-2">Lançamentos</div>
      {!loading && items.length === 0 ? <Empty text="Nenhum lançamento." /> : (
        <div className="space-y-1.5">
          {items.map((c) => (
            <div key={c.id} className="card !p-3 flex justify-between items-center gap-2">
              <div className="min-w-0">
                <div className="text-sm font-medium truncate">{c.partner_name} <span className="text-[11px] text-text-muted">· {brl(c.commission_amount)}</span></div>
                <div className="text-[11px] text-text-muted truncate">
                  {c.coupon_code || '—'} · base {brl(c.base_amount)} · {c.customer_email || 'cliente'} · <span className={COMMISSION_STATUS_COLOR[c.status]}>{COMMISSION_STATUS_LABELS[c.status]}</span>
                </div>
              </div>
              {c.status === 'pending' && (
                <div className="flex gap-1 shrink-0">
                  <button className="text-green-400 border border-green-400/40 rounded px-2 py-1 text-xs" title="Aprovar" disabled={acting} onClick={() => changeStatus(c.id, 'approved')}><Check className="w-3 h-3" /></button>
                  <button className="text-red-400 border border-red-400/40 rounded px-2 py-1 text-xs" title="Cancelar" disabled={acting} onClick={() => changeStatus(c.id, 'canceled')}><Ban className="w-3 h-3" /></button>
                </div>
              )}
              {c.status === 'approved' && (
                <button className="text-red-400 border border-red-400/40 rounded px-2 py-1 text-xs shrink-0" title="Cancelar" disabled={acting} onClick={() => changeStatus(c.id, 'canceled')}><Ban className="w-3 h-3" /></button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ─── Repasses ────────────────────────────────────────────────────────────────────

const PayoutsSection: React.FC = () => {
  const [items, setItems] = useState<Payout[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { setItems((await listPayouts()).results); }
    catch (e) { toast.error(extractApiError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <button className="btn-secondary !text-xs" onClick={load}><RefreshCcw className="w-3 h-3 inline mr-1" />Atualizar</button>
      </div>
      {loading ? <Spinner /> : items.length === 0 ? <Empty text="Nenhum repasse registrado." /> : (
        <div className="space-y-1.5">
          {items.map((p) => (
            <div key={p.id} className="card !p-3 flex justify-between items-center">
              <div>
                <div className="text-sm font-medium">{p.partner_name} <span className="text-[11px] text-text-muted">· {brl(p.amount)}</span></div>
                <div className="text-[11px] text-text-muted">{p.commissions_count} comissão(ões) · {p.method || '—'} · {p.reference || 'sem ref.'} · {fmtDate(p.paid_at)}</div>
              </div>
              <span className="text-xs text-green-400">{p.status === 'paid' ? 'Pago' : p.status}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
