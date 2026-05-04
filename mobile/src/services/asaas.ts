/**
 * Asaas client-side card tokenization.
 *
 * PCI-DSS compliance: raw card data (number, CVV, expiry) is sent DIRECTLY
 * to Asaas from the mobile device — our backend NEVER sees card numbers.
 * Only the returned creditCardToken is sent to our backend.
 *
 * Reference: https://docs.asaas.com/reference/tokenizar-cartao-de-credito
 */
import axios from 'axios';

const ASAAS_SANDBOX = 'https://sandbox.asaas.com/api/v3';
const ASAAS_PRODUCTION = 'https://api.asaas.com/v3';

function getAsaasBaseUrl(): string {
  // Use production URL only in production builds
  if (!__DEV__ && process.env.EXPO_PUBLIC_ASAAS_ENV === 'production') {
    return ASAAS_PRODUCTION;
  }
  return ASAAS_SANDBOX;
}

export interface CardData {
  holderName: string;
  number: string;
  expiryMonth: string;
  expiryYear: string;
  ccv: string;
}

export interface CardHolderInfo {
  name: string;
  email: string;
  cpfCnpj: string;
  postalCode: string;
  phone?: string;
}

export interface AsaasTokenizeResponse {
  creditCardToken: string;
  creditCardBrand: string;
  creditCardNumber: string; // masked, e.g. "xxxx-xxxx-xxxx-1234"
}

/**
 * Tokenize a credit/debit card directly with Asaas.
 * Returns a creditCardToken that can be safely sent to our backend.
 *
 * NEVER call this through our backend — the card data must go directly
 * to Asaas to maintain PCI-DSS SAQ A-EP compliance.
 */
export async function tokenizeCard(
  card: CardData,
  holderInfo: CardHolderInfo,
  customerId: string,
): Promise<AsaasTokenizeResponse> {
  const baseUrl = getAsaasBaseUrl();
  // NOTE: The tokenization endpoint does NOT require an API key from the client
  // per Asaas documentation — it uses the customer ID as identifier.
  const response = await axios.post(
    `${baseUrl}/creditCard/tokenize`,
    {
      customer: customerId,
      creditCard: {
        holderName: card.holderName.trim().toUpperCase(),
        number: card.number.replace(/\s/g, ''),
        expiryMonth: card.expiryMonth.padStart(2, '0'),
        expiryYear: card.expiryYear.length === 2 ? `20${card.expiryYear}` : card.expiryYear,
        ccv: card.ccv,
      },
      creditCardHolderInfo: {
        name: holderInfo.name.trim(),
        email: holderInfo.email,
        cpfCnpj: holderInfo.cpfCnpj.replace(/\D/g, ''),
        postalCode: holderInfo.postalCode.replace(/\D/g, ''),
        addressNumber: '0',
        phone: holderInfo.phone?.replace(/\D/g, '') || '',
      },
    },
    {
      timeout: 30000,
      headers: { 'Content-Type': 'application/json' },
    },
  );
  return response.data as AsaasTokenizeResponse;
}

/**
 * Get or create the Asaas customer ID for the current user.
 * Our backend handles this and returns the customer ID.
 */
export async function getAsaasCustomerId(apiClient: any, userId: number): Promise<string | null> {
  try {
    const res = await apiClient.get('/api/billing/asaas-customer-id/');
    return res.data?.customer_id || null;
  } catch {
    return null;
  }
}
