import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import App from './App';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { ErrorBoundary } from './components/ErrorBoundary';
import './styles/globals.css';

// Without a root boundary, any uncaught rendering error unmounts the whole
// tree and the user is left staring at an empty page with no way out.
const rootErrorFallback = () => (
  <div className="min-h-screen bg-bg-base flex items-center justify-center text-center px-4">
    <div>
      <p className="text-sm font-semibold text-text-primary mb-1">Não foi possível carregar a página.</p>
      <p className="text-xs text-text-muted mb-4">Pode ser uma versão desatualizada em cache. Recarregue para continuar.</p>
      <button
        onClick={() => window.location.reload()}
        className="btn-secondary text-xs !py-1.5 !px-4"
      >
        Recarregar
      </button>
    </div>
  </div>
);

// When a new service worker activates (skipWaiting), reload the page so users
// immediately see the new version instead of needing incognito / manual clear.
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    window.location.reload();
  });
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <ErrorBoundary fallback={rootErrorFallback}>
            <App />
          </ErrorBoundary>
          <Toaster
            position="top-center"
            toastOptions={{
              className: '!bg-bg-card !text-text-primary !border !border-border-subtle !rounded-xl',
              success: { iconTheme: { primary: '#3DC55E', secondary: 'rgb(var(--bg-base))' } },
              error:   { iconTheme: { primary: '#FF5A5A', secondary: 'rgb(var(--bg-base))' } },
            }}
          />
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
