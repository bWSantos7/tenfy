import { TournamentEditionDetail, TournamentEditionList } from '../types';

export type AuthStackParamList = {
  Login: undefined;
  Register: undefined;
  ForgotPassword: undefined;
};

export type MainTabParamList = {
  Home: undefined;
  Tournaments: { circuit?: string; organization?: number } | undefined;
  Watchlist: undefined;
  Results: undefined;
  Alerts: undefined;
  Profile: undefined;
};

export type MainStackParamList = {
  Tabs: undefined;
  TournamentDetail: { id: number; edition?: TournamentEditionList | TournamentEditionDetail };
  Onboarding: undefined;
  Coach: undefined;
  AdminPanel: undefined;
  MyRegistrations: undefined;
  RegistrationList: { editionId: number; editionTitle: string };
  Plans: undefined;
  Checkout: { plan: import('../types/billing').Plan; billingPeriod: 'monthly' | 'yearly' };
  PixPayment: { pixData: import('../types/billing').PixPaymentData };
  Subscription: undefined;
  TournamentCompare: { ids: number[] };
};
