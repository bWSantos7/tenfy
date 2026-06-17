import React, { Suspense } from 'react';
import { Route, Routes } from 'react-router-dom';
import { AppLayout } from './components/AppLayout';
import { ProtectedRoute, PublicOnlyRoute } from './components/ProtectedRoute';

// After a deploy, a tab still running the previous bundle may lazy-load a
// chunk that no longer exists on the server (the host answers with index.html,
// which fails the import). Reloading fetches the fresh index.html and heals
// the session; the timestamp guard avoids a reload loop if the server itself
// is misbehaving.
const CHUNK_RELOAD_KEY = 'tenfy-chunk-reload-at';
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function lazyPage<T extends React.ComponentType<any>>(load: () => Promise<{ default: T }>) {
  return React.lazy(() =>
    load().catch((err) => {
      const last = Number(sessionStorage.getItem(CHUNK_RELOAD_KEY) || 0);
      if (Date.now() - last > 15_000) {
        sessionStorage.setItem(CHUNK_RELOAD_KEY, String(Date.now()));
        window.location.reload();
      }
      throw err;
    }),
  );
}

const LoginPage           = lazyPage(() => import('./pages/LoginPage').then(m => ({ default: m.LoginPage })));
const RegisterPage        = lazyPage(() => import('./pages/RegisterPage').then(m => ({ default: m.RegisterPage })));
const ForgotPasswordPage  = lazyPage(() => import('./pages/ForgotPasswordPage').then(m => ({ default: m.ForgotPasswordPage })));
const ResetPasswordPage   = lazyPage(() => import('./pages/ResetPasswordPage').then(m => ({ default: m.ResetPasswordPage })));
const OnboardingPage      = lazyPage(() => import('./pages/OnboardingPage').then(m => ({ default: m.OnboardingPage })));
const HomePage            = lazyPage(() => import('./pages/HomePage').then(m => ({ default: m.HomePage })));
const LandingPage         = lazyPage(() => import('./pages/LandingPage').then(m => ({ default: m.LandingPage })));
const TournamentsPage     = lazyPage(() => import('./pages/TournamentsPage').then(m => ({ default: m.TournamentsPage })));
const TournamentDetailPage = lazyPage(() => import('./pages/TournamentDetailPage').then(m => ({ default: m.TournamentDetailPage })));
const WatchlistPage       = lazyPage(() => import('./pages/WatchlistPage').then(m => ({ default: m.WatchlistPage })));
const AlertsPage          = lazyPage(() => import('./pages/AlertsPage').then(m => ({ default: m.AlertsPage })));
const PlayerProfilePage   = lazyPage(() => import('./pages/PlayerProfilePage').then(m => ({ default: m.PlayerProfilePage })));
const ProfilePage         = lazyPage(() => import('./pages/ProfilePage').then(m => ({ default: m.ProfilePage })));
const AdminPanelPage      = lazyPage(() => import('./pages/AdminPanelPage').then(m => ({ default: m.AdminPanelPage })));
const ResultsPage         = lazyPage(() => import('./pages/ResultsPage').then(m => ({ default: m.ResultsPage })));
const CoachPage           = lazyPage(() => import('./pages/CoachPage').then(m => ({ default: m.CoachPage })));
const SubscriptionPage    = lazyPage(() => import('./pages/SubscriptionPage').then(m => ({ default: m.SubscriptionPage })));
const PaymentReturnPage   = lazyPage(() => import('./pages/PaymentReturnPage').then(m => ({ default: m.PaymentReturnPage })));
const PrivacyPolicyPage   = lazyPage(() => import('./pages/PrivacyPolicyPage').then(m => ({ default: m.PrivacyPolicyPage })));
const AccountDeletionPage = lazyPage(() => import('./pages/AccountDeletionPage').then(m => ({ default: m.AccountDeletionPage })));
const InscricoesPage      = lazyPage(() => import('./pages/InscricoesPage').then(m => ({ default: m.InscricoesPage })));
const TournamentComparePage = lazyPage(() => import('./pages/TournamentComparePage').then(m => ({ default: m.TournamentComparePage })));

const PageLoader: React.FC = () => (
  <div className="min-h-screen bg-bg-base flex items-center justify-center">
    <div className="w-8 h-8 border-2 border-accent-neon border-t-transparent rounded-full animate-spin" />
  </div>
);

const App: React.FC = () => {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route
          path="/login"
          element={
            <PublicOnlyRoute>
              <LoginPage />
            </PublicOnlyRoute>
          }
        />
        {/* /register is NOT wrapped in PublicOnlyRoute: after step-1 (account creation)
            the user is authenticated but needs to stay on this page to complete OTP steps.
            setUser() is only called after all OTP verification is done. */}
        <Route path="/register" element={<RegisterPage />} />
        <Route
          path="/recuperar-senha"
          element={
            <PublicOnlyRoute>
              <ForgotPasswordPage />
            </PublicOnlyRoute>
          }
        />
        <Route
          path="/redefinir-senha/:uid/:token"
          element={
            <PublicOnlyRoute>
              <ResetPasswordPage />
            </PublicOnlyRoute>
          }
        />
        <Route
          path="/onboarding"
          element={
            <ProtectedRoute>
              <OnboardingPage />
            </ProtectedRoute>
          }
        />

        <Route path="/" element={<LandingPage />} />

        <Route
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        >
          <Route path="inicio" element={<HomePage />} />
          <Route path="torneios" element={<TournamentsPage />} />
          <Route path="torneios/:id" element={<TournamentDetailPage />} />
          <Route path="comparar" element={<TournamentComparePage />} />
          <Route path="watchlist" element={<WatchlistPage />} />
          <Route path="resultados" element={<ResultsPage />} />
          <Route path="alertas" element={<AlertsPage />} />
          <Route path="perfil" element={<PlayerProfilePage />} />
          <Route path="configuracoes" element={<ProfilePage />} />
          <Route path="assinatura" element={<SubscriptionPage />} />
          <Route path="inscricoes" element={<InscricoesPage />} />
          <Route path="treinador" element={<CoachPage />} />
          <Route
            path="admin-panel"
            element={
              <ProtectedRoute admin>
                <AdminPanelPage />
              </ProtectedRoute>
            }
          />
        </Route>

        {/* Retorno do pagamento (Asaas) — fora do app (sem nav/paywall). */}
        <Route
          path="/pagamento"
          element={
            <ProtectedRoute>
              <PaymentReturnPage />
            </ProtectedRoute>
          }
        />

        <Route path="/politica-privacidade" element={<PrivacyPolicyPage />} />

        {/* Página pública de exclusão de conta (exigida pelas lojas de apps). */}
        <Route path="/exclusao-de-conta" element={<AccountDeletionPage />} />
        <Route path="/excluir-conta" element={<AccountDeletionPage />} />

        <Route
          path="*"
          element={
            <div className="min-h-screen bg-bg-base flex items-center justify-center text-center px-4">
              <div>
                <h1 className="text-4xl font-bold text-accent-neon mb-2">404</h1>
                <p className="text-text-secondary">Página não encontrada.</p>
                <a href="/" className="text-accent-blue hover:underline text-sm mt-2 inline-block">
                  Voltar ao início
                </a>
              </div>
            </div>
          }
        />
      </Routes>
    </Suspense>
  );
};

export default App;
