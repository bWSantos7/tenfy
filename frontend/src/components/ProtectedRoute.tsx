import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Loader2 } from 'lucide-react';

const Spinner: React.FC = () => (
  <div className="min-h-screen flex items-center justify-center bg-bg-base">
    <Loader2 className="w-8 h-8 text-accent-neon animate-spin" />
  </div>
);

export const ProtectedRoute: React.FC<{ children: React.ReactNode; admin?: boolean }> = ({
  children, admin = false,
}) => {
  const { isAuthenticated, loading, user } = useAuth();
  const location = useLocation();

  if (loading) return <Spinner />;
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  // Parceiro não acessa o app do jogador — vai para sua área exclusiva.
  if (user?.role === 'partner') {
    return <Navigate to="/parceiro" replace />;
  }
  if (admin && !user?.is_staff) {
    return <Navigate to="/inicio" replace />;
  }
  return <>{children}</>;
};

/** Área exclusiva do parceiro: exige conta autenticada com role=partner. */
export const PartnerRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, loading, user } = useAuth();
  if (loading) return <Spinner />;
  if (!isAuthenticated || user?.role !== 'partner') {
    return <Navigate to="/parceiro/login" replace />;
  }
  return <>{children}</>;
};

export const PublicOnlyRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, loading, user } = useAuth();
  if (loading) return null;
  if (isAuthenticated) {
    return <Navigate to={user?.role === 'partner' ? '/parceiro' : '/inicio'} replace />;
  }
  return <>{children}</>;
};
