import api from './api';

export interface PlanFeature {
  code: string;
  name: string;
  limit: number | null;
}

export interface Plan {
  id: number;
  name: string;
  slug: 'tester' | 'free' | 'individual' | 'familia';
  price_monthly: string;
  price_yearly: string;
  description: string;
  highlight_label: string;
  display_order: number;
  is_active: boolean;
  max_members: number;
  features: PlanFeature[];
}

export interface Subscription {
  id: number;
  plan: number;
  plan_name: string;
  plan_slug: 'individual' | 'familia';
  billing_period: 'monthly' | 'yearly';
  status: 'pending' | 'active' | 'canceled' | 'expired' | 'unpaid' | 'trial';
  is_active: boolean;
  pending_plan: number | null;
  pending_billing_period: string;
  start_date: string | null;
  next_due_date: string | null;
  cancel_at_period_end: boolean;
  canceled_at: string | null;
  asaas_subscription_id: string;
  price_monthly: string;
  price_yearly: string;
  created_at: string;
  updated_at: string;
}

export interface CheckoutResponse extends Subscription {
  pix?: {
    qr_code_image: string;
    copia_e_cola: string;
    expiration: string;
  };
  asaas?: { id: string; [key: string]: unknown };
}

export interface FamilyMember {
  id: number;
  member_email: string;
  member_name: string;
  status: 'pending' | 'active' | 'removed';
  accepted_at: string | null;
  created_at: string;
}

export async function fetchPlans(): Promise<Plan[]> {
  const res = await api.get('/api/billing/plans/');
  return res.data;
}

export async function fetchSubscription(): Promise<Subscription> {
  const res = await api.get('/api/billing/subscription/');
  return res.data;
}

export async function checkout(payload: {
  plan_slug: 'individual' | 'familia';
  billing_period?: 'monthly' | 'yearly';
  payment_method?: 'pix' | 'credit_card' | 'debit_card';
  card_token?: string;
}): Promise<CheckoutResponse> {
  const res = await api.post('/api/billing/subscription/checkout/', payload);
  return res.data;
}

export async function cancelSubscription(immediate = false): Promise<Subscription> {
  const res = await api.post('/api/billing/subscription/cancel/', { immediate });
  return res.data;
}

export async function reactivateSubscription(): Promise<Subscription> {
  const res = await api.post('/api/billing/subscription/reactivate/');
  return res.data;
}

// ── Família — gestão de dependentes ─────────────────────────────────────────

export async function listFamilyMembers(): Promise<FamilyMember[]> {
  const res = await api.get('/api/billing/family/members/');
  return res.data;
}

export async function addFamilyMember(payload: { email?: string; user_id?: number }): Promise<FamilyMember> {
  const res = await api.post('/api/billing/family/members/', payload);
  return res.data;
}

export async function removeFamilyMember(id: number): Promise<void> {
  await api.delete(`/api/billing/family/members/${id}/`);
}

export async function acceptFamilyInvite(id: number): Promise<FamilyMember> {
  const res = await api.post(`/api/billing/family/members/${id}/`);
  return res.data;
}
