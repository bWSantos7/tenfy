import React from 'react';
import { Route, Routes } from 'react-router-dom';
import { AppLayout } from './components/AppLayout';
import { ProtectedRoute, PublicOnlyRoute } from './components/ProtectedRoute';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { ForgotPasswordPage } from './pages/ForgotPasswordPage';
import { ResetPasswordPage } from './pages/ResetPasswordPage';
import { OnboardingPage } from './pages/OnboardingPage';
import { HomePage } from './pages/HomePage';
import { TournamentsPage } from './pages/TournamentsPage';
import { TournamentDetailPage } from './pages/TournamentDetailPage';
import { WatchlistPage } from './pages/WatchlistPage';
import { AlertsPage } from './pages/AlertsPage';
import { ProfilePage } from './pages/ProfilePage';
import { AdminPanelPage } from './pages/AdminPanelPage';
import { ResultsPage } from './pages/ResultsPage';
import { CoachPage } from './pages/CoachPage';
import { SubscriptionPage } from './pages/SubscriptionPage';

const App: React.FC = () => {
  return (
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

      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<HomePage />} />
        <Route path="torneios" element={<TournamentsPage />} />
        <Route path="torneios/:id" element={<TournamentDetailPage />} />
        <Route path="watchlist" element={<WatchlistPage />} />
        <Route path="resultados" element={<ResultsPage />} />
        <Route path="alertas" element={<AlertsPage />} />
        <Route path="perfil" element={<ProfilePage />} />
        <Route path="assinatura" element={<SubscriptionPage />} />
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
  );
};

export default App;
