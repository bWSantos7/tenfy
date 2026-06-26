import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, LogOut, Moon, Sun, Ticket, Users, Wallet } from 'lucide-react';
import toast from 'react-hot-toast';
import { extractApiError } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import {
  PartnerMe, PartnerDashboard, PartnerCoupon, PartnerUsage,
  fetchPartnerMe, fetchPartnerDashboard, fetchPartnerCoupons, fetchPartnerUsages,
} from '../services/partner';

function brl(value: string | number): string {
  const num = typeof value === 'number' ? value : parseFloat(value);
  if (Number.isNaN(num)) return 'R$ 0,00';
  return `R$ ${num.toFixed(2).replace('.', ',')}`;
}

function formatDate(d: string | null): string {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('pt-BR');
}

const COUPON_STATUS: Record<string, { label: string; color: string }> = {
  active:    { label: 'Ativo',     color: 'text-green-400' },
  draft:     { label: 'Rascunho',  color: 'text-text-muted' },
  inactive:  { label: 'Inativo',   color: 'text-gray-400' },
  expired:   { label: 'Expirado',  color: 'text-amber-400' },
  exhausted: { label: 'Esgotado',  color: 'text-amber-400' },
};

const USAGE_STATUS: Record<string, { label: string; color: string }> = {
  pending:  { label: 'Pendente',  color: 'text-amber-400' },
  approved: { label: 'Aprovada',  color: 'text-blue-400' },
  paid:     { label: 'Paga',      color: 'text-green-400' },
  reversed: { label: 'Revertida', color: 'text-red-400' },
  canceled: { label: 'Cancelada', color: 'text-gray-400' },
};

function ruleLabel(c: PartnerCoupon): string {
  const disc = c.discount_type === 'percent'
    ? `${parseFloat(c.discount_value)}% off`
    : `${brl(c.discount_value)} off`;
  if (!c.rule) return disc;
  const com = c.rule.commission_type === 'percent'
    ? `${parseFloat(c.rule.commission_value)}% comissão`
    : `${brl(c.rule.commission_value)} comissão`;
  return `${disc} · ${com}`;
}

const Kpi: React.FC<{ icon: React.ReactNode; label: string; value: string; hint?: string }> = ({
  icon, label, value, hint,
}) => (
  <div className="card !p-4">
    <div className="flex items-center gap-2 text-text-muted text-xs">{icon}{label}</div>
    <div className="text-xl font-bold mt-1">{value}</div>
    {hint && <div className="text-[11px] text-text-muted mt-0.5">{hint}</div>}
  </div>
);

export const PartnerDashboardPage: React.FC = () => {
  const nav = useNavigate();
  const { logout } = useAuth();
  const { theme, toggle: toggleTheme } = useTheme();
  const [me, setMe] = useState<PartnerMe | null>(null);
  const [dash, setDash] = useState<PartnerDashboard | null>(null);
  const [coupons, setCoupons] = useState<PartnerCoupon[]>([]);
  const [usages, setUsages] = useState<PartnerUsage[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [m, d, c, u] = await Promise.all([
        fetchPartnerMe(),
        fetchPartnerDashboard(),
        fetchPartnerCoupons(),
        fetchPartnerUsages(),
      ]);
      setMe(m); setDash(d); setCoupons(c); setUsages(u);
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleLogout() {
    await logout();
    nav('/parceiro/login', { replace: true });
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-bg-base flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-accent-neon animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg-base">
      <header className="border-b border-border-subtle">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <img src="/logos/logo_clara.png" alt="Tenfy" className="h-8 w-auto object-contain dark:hidden" />
            <img src="/logos/logo_escura.png" alt="Tenfy" className="h-6 w-auto object-contain hidden dark:block" />
            <div className="min-w-0">
              <div className="text-sm font-semibold truncate">{me?.name || 'Parceiro'}</div>
              <div className="text-[11px] text-text-muted truncate">{me?.login_email}</div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={toggleTheme}
              className="btn-secondary !text-xs !px-2"
              title={theme === 'dark' ? 'Modo claro' : 'Modo escuro'}
            >
              {theme === 'dark' ? <Sun className="w-4 h-4 text-accent-neon" /> : <Moon className="w-4 h-4" />}
            </button>
            <button className="btn-secondary !text-xs flex items-center gap-1" onClick={handleLogout}>
              <LogOut className="w-3.5 h-3.5" /> Sair
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-5 space-y-5">
        <div>
          <h1 className="text-xl font-bold">Seus resultados</h1>
          <p className="text-sm text-text-muted">Acompanhe os cupons e o que eles geraram.</p>
        </div>

        {/* KPIs */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Kpi icon={<Wallet className="w-4 h-4" />} label="Comissão a receber" value={brl(dash?.commission_payable || 0)}
               hint={`${brl(dash?.commission_paid || 0)} já paga`} />
          <Kpi icon={<Users className="w-4 h-4" />} label="Conversões" value={String(dash?.total_conversions ?? 0)}
               hint="assinaturas via seus cupons" />
          <Kpi icon={<Ticket className="w-4 h-4" />} label="Cupons ativos" value={String(dash?.active_coupons ?? 0)}
               hint={`${dash?.total_coupons ?? 0} no total`} />
        </div>

        {/* Cupons */}
        <section className="space-y-2">
          <h2 className="text-sm font-semibold">Seus cupons</h2>
          {coupons.length === 0 ? (
            <div className="card !p-6 text-center text-sm text-text-muted">
              Você ainda não possui cupons vinculados.
            </div>
          ) : (
            <div className="grid sm:grid-cols-2 gap-3">
              {coupons.map((c) => {
                const st = COUPON_STATUS[c.status] ?? { label: c.status, color: 'text-text-muted' };
                return (
                  <div key={c.id} className="card !p-4 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono font-bold text-accent-neon">{c.code}</span>
                      <span className={`text-xs font-semibold ${st.color}`}>{st.label}</span>
                    </div>
                    <div className="text-xs text-text-muted">{ruleLabel(c)}</div>
                    <div className="grid grid-cols-3 gap-2 text-xs pt-1">
                      <div>
                        <div className="text-text-muted">Usos</div>
                        <div className="font-semibold">
                          {c.times_used}{c.max_total_uses ? ` / ${c.max_total_uses}` : ''}
                        </div>
                      </div>
                      <div>
                        <div className="text-text-muted">Conversões</div>
                        <div className="font-semibold">{c.conversions}</div>
                      </div>
                      <div>
                        <div className="text-text-muted">Comissão</div>
                        <div className="font-semibold">{brl(c.commission)}</div>
                      </div>
                    </div>
                    {c.expires_at && (
                      <div className="text-[11px] text-text-muted">Expira em {formatDate(c.expires_at)}</div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Histórico de uso */}
        <section className="space-y-2">
          <h2 className="text-sm font-semibold">Histórico de uso</h2>
          {usages.length === 0 ? (
            <div className="card !p-6 text-center text-sm text-text-muted">
              Nenhum uso de cupom registrado ainda.
            </div>
          ) : (
            <div className="card !p-0 overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-text-muted border-b border-border-subtle">
                    <th className="text-left font-medium px-3 py-2">Data</th>
                    <th className="text-left font-medium px-3 py-2">Cupom</th>
                    <th className="text-left font-medium px-3 py-2">Quem usou</th>
                    <th className="text-right font-medium px-3 py-2">Comissão</th>
                    <th className="text-right font-medium px-3 py-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {usages.map((u) => {
                    const st = USAGE_STATUS[u.status] ?? { label: u.status, color: 'text-text-muted' };
                    return (
                      <tr key={u.id} className="border-b border-border-subtle/50 last:border-0">
                        <td className="px-3 py-2 whitespace-nowrap">{formatDate(u.created_at)}</td>
                        <td className="px-3 py-2 font-mono">{u.coupon_code || '—'}</td>
                        <td className="px-3 py-2 truncate max-w-[180px]">{u.customer_email || '—'}</td>
                        <td className="px-3 py-2 text-right whitespace-nowrap">{brl(u.commission_amount)}</td>
                        <td className={`px-3 py-2 text-right whitespace-nowrap font-semibold ${st.color}`}>{st.label}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </div>
  );
};
