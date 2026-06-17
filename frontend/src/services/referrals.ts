import api from './api';

// ─── Tipos ───────────────────────────────────────────────────────────────────

export type PartnerType = 'influencer' | 'coach' | 'academy' | 'ambassador' | 'other';
export type PartnerStatus = 'active' | 'inactive';
export type DiscountType = 'percent' | 'fixed';
export type PlanScope = 'individual' | 'familia' | 'both';
export type CouponStatus = 'draft' | 'active' | 'inactive' | 'expired' | 'exhausted';
export type RuleScope = 'first_payment' | 'all_payments';
export type BaseAmountType = 'net_paid' | 'gross_paid';
export type RuleStatus = 'active' | 'inactive';
export type CommissionStatus = 'pending' | 'approved' | 'paid' | 'reversed' | 'canceled';
export type PayoutStatus = 'draft' | 'processing' | 'paid' | 'failed' | 'canceled';

export interface Partner {
  id: number;
  name: string;
  type: PartnerType;
  email: string;
  phone: string;
  status: PartnerStatus;
  payout_method: string;
  payout_details: string;
  notes: string;
  coupons_count: number;
  created_at: string;
  updated_at: string;
}

export interface Coupon {
  id: number;
  code: string;
  partner: number;
  partner_name: string;
  discount_type: DiscountType;
  discount_value: string;
  plan_scope: PlanScope;
  starts_at: string | null;
  expires_at: string | null;
  max_total_uses: number | null;
  max_uses_per_customer: number | null;
  times_used: number;
  status: CouponStatus;
  created_at: string;
  updated_at: string;
}

export interface CommissionRule {
  id: number;
  partner: number;
  partner_name: string;
  coupon: number | null;
  coupon_code: string | null;
  commission_type: DiscountType;
  commission_value: string;
  rule_scope: RuleScope;
  base_amount_type: BaseAmountType;
  status: RuleStatus;
  created_at: string;
  updated_at: string;
}

export interface Commission {
  id: number;
  partner: number;
  partner_name: string;
  coupon: number | null;
  coupon_code: string | null;
  subscription: number | null;
  payment: number | null;
  commission_rule: number | null;
  payout: number | null;
  customer_email: string | null;
  base_amount: string;
  commission_amount: string;
  status: CommissionStatus;
  created_at: string;
  updated_at: string;
}

export interface Payout {
  id: number;
  partner: number;
  partner_name: string;
  amount: string;
  status: PayoutStatus;
  method: string;
  reference: string;
  notes: string;
  paid_at: string | null;
  commissions_count: number;
  created_at: string;
  updated_at: string;
}

export interface CommissionSummaryRow {
  partner_id: number;
  partner_name: string;
  total_count: number;
  pending_amount: string;
  approved_amount: string;
  paid_amount: string;
  reversed_amount: string;
  payable_amount: string;
}

interface ListResponse<T> { count: number; results: T[] }

const BASE = '/api/admin-panel';

// ─── Parceiros ─────────────────────────────────────────────────────────────────

export async function listPartners(params?: { q?: string; status?: string }): Promise<ListResponse<Partner>> {
  const res = await api.get(`${BASE}/partners/`, { params });
  return res.data;
}
export async function createPartner(payload: Partial<Partner>): Promise<Partner> {
  const res = await api.post(`${BASE}/partners/`, payload);
  return res.data;
}
export async function updatePartner(id: number, payload: Partial<Partner>): Promise<Partner> {
  const res = await api.patch(`${BASE}/partners/${id}/`, payload);
  return res.data;
}
export async function deletePartner(id: number): Promise<void> {
  await api.delete(`${BASE}/partners/${id}/`);
}

// ─── Cupons ────────────────────────────────────────────────────────────────────

export async function listCoupons(params?: { partner?: number; status?: string; q?: string }): Promise<ListResponse<Coupon>> {
  const res = await api.get(`${BASE}/coupons/`, { params });
  return res.data;
}
export async function createCoupon(payload: Partial<Coupon>): Promise<Coupon> {
  const res = await api.post(`${BASE}/coupons/`, payload);
  return res.data;
}
export async function updateCoupon(id: number, payload: Partial<Coupon>): Promise<Coupon> {
  const res = await api.patch(`${BASE}/coupons/${id}/`, payload);
  return res.data;
}
export async function deleteCoupon(id: number): Promise<void> {
  await api.delete(`${BASE}/coupons/${id}/`);
}

// ─── Regras de comissão ──────────────────────────────────────────────────────────

export async function listCommissionRules(params?: { partner?: number }): Promise<ListResponse<CommissionRule>> {
  const res = await api.get(`${BASE}/commission-rules/`, { params });
  return res.data;
}
export async function createCommissionRule(payload: Partial<CommissionRule>): Promise<CommissionRule> {
  const res = await api.post(`${BASE}/commission-rules/`, payload);
  return res.data;
}
export async function updateCommissionRule(id: number, payload: Partial<CommissionRule>): Promise<CommissionRule> {
  const res = await api.patch(`${BASE}/commission-rules/${id}/`, payload);
  return res.data;
}
export async function deleteCommissionRule(id: number): Promise<void> {
  await api.delete(`${BASE}/commission-rules/${id}/`);
}

// ─── Comissões ───────────────────────────────────────────────────────────────────

export async function listCommissions(params?: { partner?: number; status?: string }): Promise<ListResponse<Commission>> {
  const res = await api.get(`${BASE}/commissions/`, { params });
  return res.data;
}
export async function updateCommissionStatus(id: number, status: CommissionStatus): Promise<Commission> {
  const res = await api.patch(`${BASE}/commissions/${id}/`, { status });
  return res.data;
}
export async function commissionsSummary(): Promise<ListResponse<CommissionSummaryRow>> {
  const res = await api.get(`${BASE}/commissions/summary/`);
  return res.data;
}

// ─── Repasses ────────────────────────────────────────────────────────────────────

export async function listPayouts(params?: { partner?: number }): Promise<ListResponse<Payout>> {
  const res = await api.get(`${BASE}/payouts/`, { params });
  return res.data;
}
export async function createPayout(payload: {
  partner: number; method?: string; reference?: string; notes?: string; commission_ids?: number[];
}): Promise<Payout> {
  const res = await api.post(`${BASE}/payouts/`, payload);
  return res.data;
}
export async function deletePayout(id: number): Promise<void> {
  await api.delete(`${BASE}/payouts/${id}/`);
}
