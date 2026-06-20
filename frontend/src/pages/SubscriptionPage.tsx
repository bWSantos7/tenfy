import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, CreditCard, Loader2, Tag, Trash2, UserPlus, X } from 'lucide-react';
import toast from 'react-hot-toast';
import { extractApiError } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { fetchMe } from '../services/auth';

function maskCpf(v: string): string {
  return (v || '').replace(/\D/g, '').slice(0, 11)
    .replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d{1,2})$/, '$1-$2');
}
import {
  Plan,
  Subscription,
  CheckoutResponse,
  CouponValidation,
  FamilyMember,
  fetchPlans,
  fetchSubscription,
  checkout,
  createCheckoutSession,
  validateCoupon,
  cancelSubscription,
  reactivateSubscription,
  listFamilyMembers,
  addFamilyMember,
  removeFamilyMember,
} from '../services/billing';

type PaidSlug = 'individual' | 'familia';
const PAID_SLUGS: PaidSlug[] = ['individual', 'familia'];

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  active:   { label: 'Ativa',        color: 'text-green-400'  },
  pending:  { label: 'Pendente',     color: 'text-amber-400'  },
  canceled: { label: 'Cancelada',    color: 'text-red-400'    },
  expired:  { label: 'Expirada',     color: 'text-gray-400'   },
  unpaid:   { label: 'Inadimplente', color: 'text-red-400'    },
  trial:    { label: 'Trial',        color: 'text-blue-400'   },
};

function formatPrice(value: string): string {
  const num = parseFloat(value);
  if (Number.isNaN(num)) return value;
  return `R$ ${num.toFixed(2).replace('.', ',')}`;
}

function formatDate(d: string | null): string {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('pt-BR');
}

export const SubscriptionPage: React.FC = () => {
  const navigate = useNavigate();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [sub, setSub] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [pix, setPix] = useState<CheckoutResponse['pix'] | null>(null);
  const [billingPeriod, setBillingPeriod] = useState<'monthly' | 'yearly'>('monthly');
  // Cupom — destrava os planos pagos e mostra o desconto.
  const [couponCode, setCouponCode] = useState('');
  const [couponResults, setCouponResults] = useState<Record<string, CouponValidation>>({});
  const [couponApplied, setCouponApplied] = useState(false);
  const [validatingCoupon, setValidatingCoupon] = useState(false);
  // CPF — usuários existentes sem CPF precisam informar antes de pagar (Asaas exige).
  const { user, setUser } = useAuth();
  const [cpf, setCpf] = useState('');
  const needsCpf = !user?.cpf;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // fetchSubscription() lança 404 quando não há assinatura — tratar como null
      const [p, s] = await Promise.all([
        fetchPlans(),
        fetchSubscription().catch(() => null),
      ]);
      setPlans(p);
      setSub(s);
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Pix gerado: enquanto aguarda a confirmação do pagamento, consulta o status
  // periodicamente. O webhook do Asaas ativa a assinatura no backend; aqui só
  // refletimos isso na tela sem o usuário precisar recarregar.
  useEffect(() => {
    if (!pix) return;
    if (sub && (sub.status === 'active' || sub.status === 'trial')) return;
    const id = setInterval(async () => {
      try {
        const s = await fetchSubscription();
        setSub(s);
        if (s.status === 'active' || s.status === 'trial') {
          setPix(null);
          toast.success('Pagamento confirmado! Assinatura ativa.');
        }
      } catch {
        // mantém aguardando — assinatura ainda não confirmada
      }
    }, 5000);
    return () => clearInterval(id);
  }, [pix, sub?.status]);

  const applyCoupon = useCallback(async (code: string, period: 'monthly' | 'yearly') => {
    const trimmed = code.trim();
    if (!trimmed) return;
    setValidatingCoupon(true);
    try {
      const results = await Promise.all(
        PAID_SLUGS.map((slug) => validateCoupon({ coupon_code: trimmed, plan_slug: slug, billing_period: period })),
      );
      const map: Record<string, CouponValidation> = {};
      PAID_SLUGS.forEach((slug, i) => { map[slug] = results[i]; });
      setCouponResults(map);
      setCouponApplied(true);
      const anyValid = results.some((r) => r.valid);
      if (anyValid) {
        toast.success('Cupom aplicado! Planos liberados abaixo.');
      } else {
        const reason = results[0]?.detail || 'Cupom inválido.';
        toast.error(reason);
      }
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setValidatingCoupon(false);
    }
  }, []);

  // Revalida o cupom quando o período muda (o desconto depende do preço do período).
  useEffect(() => {
    if (couponApplied && couponCode.trim()) {
      applyCoupon(couponCode, billingPeriod);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [billingPeriod]);

  function clearCoupon() {
    setCouponCode('');
    setCouponResults({});
    setCouponApplied(false);
  }

  // Tester: ativa na hora.
  async function handleActivateTester(plan: Plan) {
    if (acting) return;
    setActing(true);
    setPix(null);
    try {
      const res = await checkout({ plan_slug: plan.slug as 'individual' | 'familia', billing_period: billingPeriod, payment_method: 'pix' });
      setSub(res);
      toast.success('Plano ativado.');
    } catch (err) {
      toast.error(extractApiError(err));
    } finally { setActing(false); }
  }

  function cpfGuard(): 'invalid' | null {
    if (!needsCpf) return null;
    const digits = cpf.replace(/\D/g, '');
    if (digits.length !== 11) { toast.error('Informe um CPF válido para pagar.'); return 'invalid'; }
    return null;
  }

  // Plano pago via Pix: gera QR + copia-e-cola no app.
  async function handlePixCheckout(plan: Plan) {
    if (acting) return;
    if (cpfGuard() === 'invalid') return;
    setActing(true);
    setPix(null);
    try {
      const couponValid = couponResults[plan.slug]?.valid;
      const res = await checkout({
        plan_slug: plan.slug as 'individual' | 'familia',
        billing_period: billingPeriod,
        payment_method: 'pix',
        coupon_code: couponValid ? couponCode.trim() : undefined,
        cpf: needsCpf ? cpf.replace(/\D/g, '') : undefined,
      });
      setSub(res);
      if (needsCpf) { fetchMe().then(setUser).catch(() => {}); }
      if (res.pix?.copia_e_cola) {
        setPix(res.pix);
        toast.success('Pix gerado — pague para ativar.');
      } else {
        toast.error('Não foi possível gerar o Pix. Tente novamente.');
      }
    } catch (err) {
      toast.error(extractApiError(err));
    } finally { setActing(false); }
  }

  // Plano pago via cartão: redireciona para a página segura do Asaas.
  async function handleCardCheckout(plan: Plan) {
    if (acting) return;
    if (cpfGuard() === 'invalid') return;
    setActing(true);
    try {
      const couponValid = couponResults[plan.slug]?.valid;
      const session = await createCheckoutSession({
        plan_slug: plan.slug as 'individual' | 'familia',
        billing_period: billingPeriod,
        coupon_code: couponValid ? couponCode.trim() : undefined,
        cpf: needsCpf ? cpf.replace(/\D/g, '') : undefined,
      });
      if (session.checkout_url) {
        window.location.href = session.checkout_url;
      } else {
        toast.error('Não foi possível iniciar o pagamento.');
      }
    } catch (err) {
      toast.error(extractApiError(err));
    } finally { setActing(false); }
  }

  async function handleCancel(immediate: boolean) {
    if (!sub || acting) return;
    if (!window.confirm(
      immediate
        ? 'Cancelar a assinatura agora? O acesso será removido imediatamente.'
        : 'Cancelar ao final do período atual? Você manterá o acesso até o vencimento.'
    )) return;
    setActing(true);
    try {
      const updated = await cancelSubscription(immediate);
      setSub(updated);
      toast.success('Assinatura cancelada.');
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setActing(false);
    }
  }

  async function handleReactivate() {
    if (acting) return;
    setActing(true);
    try {
      const updated = await reactivateSubscription();
      setSub(updated);
      toast.success('Assinatura mantida.');
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setActing(false);
    }
  }

  if (loading) {
    return (
      <div className="py-16 flex justify-center">
        <Loader2 className="w-8 h-8 text-accent-neon animate-spin" />
      </div>
    );
  }

  const statusInfo = sub ? (STATUS_LABELS[sub.status] ?? { label: 'Status desconhecido', color: 'text-text-muted' }) : null;
  const currentPlan = plans.find((p) => p.id === sub?.plan);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Assinatura</h1>
        <p className="text-sm text-text-muted">Planos Individual e Família — pagamento via Asaas</p>
      </div>

      {/* Estado vazio — sem assinatura ativa */}
      {!sub && (
        <div className="card text-center py-10 space-y-3">
          <CreditCard className="w-10 h-10 text-text-muted mx-auto" />
          <div>
            <p className="font-semibold">Sem assinatura ativa</p>
            <p className="text-sm text-text-muted mt-1">Você ainda não possui uma assinatura ativa.</p>
          </div>
          <p className="text-xs text-text-muted">Escolha um plano abaixo para começar.</p>
        </div>
      )}

      {/* Current subscription card */}
      {sub && (
        <div className="card !p-4 space-y-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-xs text-text-muted">Plano atual</div>
              <div className="text-lg font-semibold">{sub.plan_name}</div>
              <div className="text-xs text-text-muted">
                Cobrança {sub.billing_period === 'yearly' ? 'anual' : 'mensal'}
              </div>
            </div>
            {statusInfo && (
              <span className={`text-xs font-semibold ${statusInfo.color}`}>
                {statusInfo.label}
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <div className="text-text-muted">Início</div>
              <div>{formatDate(sub.start_date)}</div>
            </div>
            <div>
              <div className="text-text-muted">Próximo vencimento</div>
              <div>{formatDate(sub.next_due_date)}</div>
            </div>
            <div>
              <div className="text-text-muted">Valor mensal</div>
              <div>{formatPrice(sub.price_monthly)}</div>
            </div>
            <div>
              <div className="text-text-muted">Valor anual</div>
              <div>{formatPrice(sub.price_yearly)}</div>
            </div>
          </div>

          {sub.cancel_at_period_end && (
            <div className="rounded border border-amber-500/40 bg-amber-500/10 text-amber-300 text-xs px-3 py-2">
              Cancelamento agendado — ativo até {formatDate(sub.next_due_date)}
            </div>
          )}

          {sub.status === 'pending' && (
            <div className="rounded border border-amber-500/40 bg-amber-500/10 text-amber-300 text-xs px-3 py-2">
              Aguardando confirmação do pagamento. Após confirmar, a assinatura ativa automaticamente.
            </div>
          )}

          <div className="flex flex-wrap gap-2 pt-1">
            {sub.is_active && !sub.cancel_at_period_end && (
              <>
                <button className="btn-secondary !text-xs" onClick={() => handleCancel(false)} disabled={acting}>
                  Cancelar no fim do período
                </button>
                <button className="btn-secondary !text-xs !text-red-400 !border-red-400/40" onClick={() => handleCancel(true)} disabled={acting}>
                  Cancelar agora
                </button>
              </>
            )}
            {sub.cancel_at_period_end && (
              <button className="btn-primary !text-xs" onClick={handleReactivate} disabled={acting}>
                Manter assinatura
              </button>
            )}
          </div>
        </div>
      )}

      {/* Pix QR/copia-e-cola */}
      {pix && (
        <div className="card !p-4 space-y-2">
          <div className="text-sm font-semibold">Pix — pagamento gerado</div>
          <div className="flex items-center gap-2 text-xs text-amber-300">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Aguardando confirmação — a tela libera sozinha assim que o pagamento cair.
          </div>
          {pix.qr_code_image && (
            <img
              src={pix.qr_code_image.startsWith('data:') ? pix.qr_code_image : `data:image/png;base64,${pix.qr_code_image}`}
              alt="QR Code Pix"
              className="w-40 h-40 mx-auto rounded border border-border-subtle"
            />
          )}
          {pix.copia_e_cola && (
            <div>
              <div className="text-xs text-text-muted mb-1">Pix copia-e-cola</div>
              <div className="flex gap-1">
                <input className="input-base text-xs flex-1" readOnly value={pix.copia_e_cola} />
                <button
                  className="btn-secondary !text-xs"
                  onClick={() => {
                    navigator.clipboard.writeText(pix.copia_e_cola);
                    toast.success('Copiado!');
                  }}
                >Copiar</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Família — gestão de dependentes */}
      {sub?.plan_slug === 'familia' && (
        <FamilySection />
      )}

      {/* Cupom — destrava os planos pagos */}
      <div className="card !p-4 space-y-2">
        <div className="flex items-center gap-1.5 text-sm font-semibold">
          <Tag className="w-4 h-4 text-accent-neon" /> Tem um cupom?
        </div>
        <div className="text-xs text-text-muted">
          Informe o cupom do seu parceiro para liberar os planos com desconto na primeira mensalidade.
        </div>
        <div className="flex gap-2">
          <input
            className="input-base flex-1 text-sm uppercase"
            placeholder="SEUCUPOM"
            value={couponCode}
            onChange={(e) => setCouponCode(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && applyCoupon(couponCode, billingPeriod)}
            disabled={validatingCoupon}
          />
          {couponApplied ? (
            <button className="btn-secondary !text-sm" onClick={clearCoupon} disabled={validatingCoupon}>
              <X className="w-4 h-4" />
            </button>
          ) : (
            <button
              className="btn-primary !text-sm"
              onClick={() => applyCoupon(couponCode, billingPeriod)}
              disabled={validatingCoupon || !couponCode.trim()}
            >
              {validatingCoupon ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Aplicar'}
            </button>
          )}
        </div>
        {couponApplied && !PAID_SLUGS.some((s) => couponResults[s]?.valid) && (
          <div className="text-xs text-red-400">
            {couponResults['individual']?.detail || 'Cupom inválido para os planos disponíveis.'}
          </div>
        )}
      </div>

      {/* CPF — necessário para pagar quando o usuário ainda não tem CPF cadastrado */}
      {needsCpf && (
        <div className="card !p-4 space-y-2">
          <div className="text-sm font-semibold">CPF para pagamento</div>
          <div className="text-xs text-text-muted">
            Para emitir a cobrança, informe seu CPF. Ele fica salvo na sua conta.
          </div>
          <input
            className="input-base w-full text-sm"
            inputMode="numeric"
            placeholder="000.000.000-00"
            value={maskCpf(cpf)}
            onChange={(e) => setCpf(e.target.value.replace(/\D/g, '').slice(0, 11))}
          />
        </div>
      )}

      {/* Plans list — checkout / upgrade */}
      <div>
        {!PAID_SLUGS.some((s) => couponResults[s]?.valid) && (
          <div className="rounded border border-amber-500/40 bg-amber-500/10 text-amber-300 text-xs px-3 py-2 mb-3">
            Os planos Individual e Família estão disponíveis apenas com cupom de parceiro no momento.
          </div>
        )}
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-semibold">Planos disponíveis</h2>
          <div className="flex gap-1 text-xs">
            {(['monthly', 'yearly'] as const).map((p) => (
              <button
                key={p}
                onClick={() => setBillingPeriod(p)}
                className={`px-2 py-1 rounded border ${
                  billingPeriod === p
                    ? 'border-accent-neon text-accent-neon bg-accent-neon/10'
                    : 'border-border-subtle text-text-muted'
                }`}
              >
                {p === 'monthly' ? 'Mensal' : 'Anual'}
              </button>
            ))}
          </div>
        </div>

        <div className="grid sm:grid-cols-2 gap-3">
          {/* Mostra o tester sempre; planos pagos só quando um cupom válido os libera. */}
          {plans
            .filter((plan) => plan.slug === 'tester' || couponResults[plan.slug]?.valid)
            .map((plan) => {
              const isCurrent = currentPlan?.id === plan.id && (sub?.is_active || sub?.status === 'pending');
              const cv = couponResults[plan.slug];
              const hasCoupon = !!cv?.valid;
              const price = billingPeriod === 'yearly' ? plan.price_yearly : plan.price_monthly;
              return (
                <div key={plan.id} className="card !p-4 space-y-3 relative">
                  {hasCoupon ? (
                    <div className="absolute -top-2 right-3 bg-accent-neon text-bg-base text-[10px] font-bold px-2 py-0.5 rounded">
                      Cupom aplicado
                    </div>
                  ) : plan.highlight_label ? (
                    <div className="absolute -top-2 right-3 bg-accent-neon text-bg-base text-[10px] font-bold px-2 py-0.5 rounded">
                      {plan.highlight_label}
                    </div>
                  ) : null}
                  <div>
                    <div className="text-base font-semibold">{plan.name}</div>
                    <div className="text-xs text-text-muted mt-1">{plan.description}</div>
                  </div>
                  <div>
                    {hasCoupon ? (
                      <>
                        <div className="flex items-baseline gap-2">
                          <span className="text-2xl font-bold text-accent-neon">{formatPrice(cv.final)}</span>
                          <span className="text-sm text-text-muted line-through">{formatPrice(cv.original)}</span>
                        </div>
                        <div className="text-[11px] text-accent-neon">
                          1ª mensalidade — economize {formatPrice(cv.discount)}
                        </div>
                        <div className="text-[11px] text-text-muted">
                          Depois {formatPrice(price)}/{billingPeriod === 'yearly' ? 'ano' : 'mês'}
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="text-2xl font-bold text-accent-neon">{formatPrice(price)}</div>
                        <div className="text-[11px] text-text-muted">/{billingPeriod === 'yearly' ? 'ano' : 'mês'}</div>
                      </>
                    )}
                  </div>
                  <ul className="space-y-1 text-xs">
                    <li className="flex items-center gap-1.5">
                      <Check className="w-3 h-3 text-accent-neon" />
                      {plan.max_members === 1 ? '1 usuário' : `Até ${plan.max_members} membros`}
                    </li>
                    {plan.features.slice(0, 5).map((f) => (
                      <li key={f.code} className="flex items-center gap-1.5">
                        <Check className="w-3 h-3 text-accent-neon" />
                        {f.name}
                      </li>
                    ))}
                  </ul>
                  {isCurrent ? (
                    <div className="text-center text-xs text-text-muted py-2 border border-border-subtle rounded">
                      Plano atual
                    </div>
                  ) : plan.slug === 'tester' ? (
                    <button className="btn-primary w-full !text-sm" onClick={() => handleActivateTester(plan)} disabled={acting}>
                      {acting ? <Loader2 className="w-4 h-4 animate-spin inline mr-1" /> : <Check className="w-4 h-4 inline mr-1" />}
                      Ativar plano
                    </button>
                  ) : (
                    <div className="space-y-1.5">
                      <button className="btn-primary w-full !text-sm" onClick={() => handlePixCheckout(plan)} disabled={acting}>
                        {acting ? <Loader2 className="w-4 h-4 animate-spin inline mr-1" /> : null}
                        Pagar com Pix
                      </button>
                      <button className="btn-secondary w-full !text-sm flex items-center justify-center gap-1" onClick={() => handleCardCheckout(plan)} disabled={acting}>
                        <CreditCard className="w-4 h-4" /> Pagar com cartão
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
        </div>

        <p className="text-[11px] text-text-muted mt-3">
          Pagamento processado pelo Asaas. Acesso liberado após confirmação do pagamento.
          Para pagamento por cartão, use o app mobile (tokenização segura).
        </p>
      </div>
    </div>
  );
};

// ── Família — gestão de dependentes ─────────────────────────────────────────

const FamilySection: React.FC = () => {
  const [members, setMembers] = useState<FamilyMember[]>([]);
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listFamilyMembers();
      setMembers(data);
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleAdd() {
    if (!email.trim() || adding) return;
    setAdding(true);
    try {
      await addFamilyMember({ email: email.trim() });
      setEmail('');
      await load();
      toast.success('Dependente adicionado.');
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setAdding(false);
    }
  }

  async function handleRemove(m: FamilyMember) {
    if (!window.confirm(`Remover ${m.member_email} da assinatura?`)) return;
    try {
      await removeFamilyMember(m.id);
      await load();
      toast.success('Dependente removido.');
    } catch (err) {
      toast.error(extractApiError(err));
    }
  }

  return (
    <div className="card !p-4 space-y-3">
      <div>
        <div className="text-sm font-semibold">Plano Família — dependentes</div>
        <div className="text-xs text-text-muted">
          Cada dependente precisa ter um cadastro no app antes de ser convidado. O titular é responsável pelo pagamento.
        </div>
      </div>

      <div className="flex gap-2">
        <input
          className="input-base flex-1 text-sm"
          type="email"
          placeholder="email@exemplo.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
        />
        <button
          className="btn-primary !text-sm"
          onClick={handleAdd}
          disabled={adding || !email.trim()}
        >
          {adding ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserPlus className="w-4 h-4" />}
        </button>
      </div>

      {loading ? (
        <Loader2 className="w-5 h-5 animate-spin mx-auto text-text-muted" />
      ) : members.length === 0 ? (
        <div className="text-xs text-text-muted text-center py-2">
          Nenhum dependente adicionado.
        </div>
      ) : (
        <div className="space-y-1.5">
          {members.map((m) => (
            <div key={m.id} className="flex items-center justify-between text-xs border-t border-border-subtle pt-1.5">
              <div>
                <div className="font-medium">{m.member_email}</div>
                <div className="text-text-muted text-[11px]">
                  {m.status === 'active' ? 'Ativo' : m.status === 'pending' ? 'Aguardando aceite' : 'Removido'}
                </div>
              </div>
              <button
                onClick={() => handleRemove(m)}
                className="text-red-400 border border-red-400/40 rounded px-2 py-1 hover:bg-red-400/10"
                title="Remover"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
