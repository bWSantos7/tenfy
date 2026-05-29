import React, { Suspense } from 'react';
import { Route, Routes } from 'react-router-dom';
import { AppLayout } from './components/AppLayout';
import { ProtectedRoute, PublicOnlyRoute } from './components/ProtectedRoute';

const LoginPage           = React.lazy(() => import('./pages/LoginPage').then(m => ({ default: m.LoginPage })));
const RegisterPage        = React.lazy(() => import('./pages/RegisterPage').then(m => ({ default: m.RegisterPage })));
const ForgotPasswordPage  = React.lazy(() => import('./pages/ForgotPasswordPage').then(m => ({ default: m.ForgotPasswordPage })));
const ResetPasswordPage   = React.lazy(() => import('./pages/ResetPasswordPage').then(m => ({ default: m.ResetPasswordPage })));
const OnboardingPage      = React.lazy(() => import('./pages/OnboardingPage').then(m => ({ default: m.OnboardingPage })));
const HomePage            = React.lazy(() => import('./pages/HomePage').then(m => ({ default: m.HomePage })));
const LandingPage         = React.lazy(() => import('./pages/LandingPage').then(m => ({ default: m.LandingPage })));
const TournamentsPage     = React.lazy(() => import('./pages/TournamentsPage').then(m => ({ default: m.TournamentsPage })));
const TournamentDetailPage = React.lazy(() => import('./pages/TournamentDetailPage').then(m => ({ default: m.TournamentDetailPage })));
const WatchlistPage       = React.lazy(() => import('./pages/WatchlistPage').then(m => ({ default: m.WatchlistPage })));
const AlertsPage          = React.lazy(() => import('./pages/AlertsPage').then(m => ({ default: m.AlertsPage })));
const PlayerProfilePage   = React.lazy(() => import('./pages/PlayerProfilePage').then(m => ({ default: m.PlayerProfilePage })));
const ProfilePage         = React.lazy(() => import('./pages/ProfilePage').then(m => ({ default: m.ProfilePage })));
const AdminPanelPage      = React.lazy(() => import('./pages/AdminPanelPage').then(m => ({ default: m.AdminPanelPage })));
const ResultsPage         = React.lazy(() => import('./pages/ResultsPage').then(m => ({ default: m.ResultsPage })));
const CoachPage           = React.lazy(() => import('./pages/CoachPage').then(m => ({ default: m.CoachPage })));
const SubscriptionPage    = React.lazy(() => import('./pages/SubscriptionPage').then(m => ({ default: m.SubscriptionPage })));
const PrivacyPolicyPage   = React.lazy(() => import('./pages/PrivacyPolicyPage').then(m => ({ default: m.PrivacyPolicyPage })));
const InscricoesPage      = React.lazy(() => import('./pages/InscricoesPage').then(m => ({ default: m.InscricoesPage })));
const TournamentComparePage = React.lazy(() => import('./pages/TournamentComparePage').then(m => ({ default: m.TournamentComparePage })));

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

        <Route path="/politica-privacidade" element={<PrivacyPolicyPage />} />

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
