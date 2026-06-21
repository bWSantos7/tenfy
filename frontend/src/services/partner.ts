import api from './api';

// Área exclusiva do parceiro — consome /api/partner/* (isolado por parceiro no backend).

export interface PartnerMe {
  id: number;
  name: string;
  type: string;
  status: string;
  login_email: string;
}

export interface PartnerDashboard {
  revenue_generated: string;
  commission_pending: string;
  commission_approved: string;
  commission_payable: string;
  commission_paid: string;
  total_conversions: number;
  active_coupons: number;
  total_coupons: number;
}

export interface PartnerCouponRule {
  commission_type: 'percent' | 'fixed';
  commission_value: string;
  rule_scope: 'first_payment' | 'all_payments';
  base_amount_type: 'net_paid' | 'gross_paid';
}

export interface PartnerCoupon {
  id: number;
  code: string;
  status: 'draft' | 'active' | 'inactive' | 'expired' | 'exhausted';
  discount_type: 'percent' | 'fixed';
  discount_value: string;
  plan_scope: 'individual' | 'familia' | 'both';
  times_used: number;
  max_total_uses: number | null;
  max_uses_per_customer: number | null;
  starts_at: string | null;
  expires_at: string | null;
  rule: PartnerCouponRule | null;
  conversions: number;
  revenue: string;
  commission: string;
}

export interface PartnerUsage {
  id: number;
  coupon_code: string | null;
  customer_email: string | null;
  base_amount: string;
  commission_amount: string;
  status: 'pending' | 'approved' | 'paid' | 'reversed' | 'canceled';
  created_at: string;
}

export async function fetchPartnerMe(): Promise<PartnerMe> {
  const res = await api.get('/api/partner/me/');
  return res.data;
}

export async function fetchPartnerDashboard(): Promise<PartnerDashboard> {
  const res = await api.get('/api/partner/dashboard/');
  return res.data;
}

export async function fetchPartnerCoupons(): Promise<PartnerCoupon[]> {
  const res = await api.get('/api/partner/coupons/');
  return res.data.results ?? [];
}

export async function fetchPartnerUsages(couponId?: number): Promise<PartnerUsage[]> {
  const res = await api.get('/api/partner/usages/', {
    params: couponId ? { coupon: couponId } : undefined,
  });
  return res.data.results ?? [];
}
