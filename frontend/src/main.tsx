import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import App from './App';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider } from './contexts/ThemeContext';
import './styles/globals.css';

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
          <App />
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
