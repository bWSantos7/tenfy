import api from './api';
import type {
  Plan,
  Subscription,
  Payment,
  FeatureAccess,
  CheckoutPayload,
  CheckoutResponse,
} from '../types/billing';
export type {
  Plan,
  PlanFeature,
  Subscription,
  Payment,
  FeatureAccess,
  CheckoutPayload,
  CheckoutResponse,
  BillingPaymentMethod,
  PixPaymentData,
} from '../types/billing';

export async function fetchPlans(): Promise<Plan[]> {
  const res = await api.get('/api/billing/plans/');
  return res.data;
}

export async function fetchSubscription(): Promise<Subscription | null> {
  try {
    const res = await api.get('/api/billing/subscription/');
    return res.data;
  } catch (err: any) {
    if (err?.response?.status === 404) return null;
    throw err;
  }
}

export async function checkout(payload: CheckoutPayload): Promise<CheckoutResponse> {
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

export async function fetchPayments(): Promise<Payment[]> {
  const res = await api.get('/api/billing/payments/');
  return res.data;
}

export async function fetchMyFeatures(): Promise<FeatureAccess> {
  const res = await api.get('/api/billing/features/');
  return res.data;
}

// ── Família ──────────────────────────────────────────────────────────────────

export interface FamilyMember {
  id: number;
  member_email: string;
  member_name: string;
  status: 'pending' | 'active' | 'removed';
  accepted_at: string | null;
  created_at: string;
}

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
