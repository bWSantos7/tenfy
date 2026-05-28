import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

const allowedHosts: string[] | true = process.env.VITE_ALLOWED_HOSTS
  ? process.env.VITE_ALLOWED_HOSTS.split(',').map((h) => h.trim())
  : true;

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icons/logo_aba.png', 'icons/*.svg'],
      manifest: {
        name: 'Tenfy',
        short_name: 'Tenfy',
        description: 'Acompanhe torneios de tênis e padel',
        theme_color: '#39ff14',
        background_color: '#0d0d0d',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        icons: [
          { src: '/icons/logo_aba.png', sizes: 'any', type: 'image/png' },
          { src: '/icons/icon-192.svg', sizes: '192x192', type: 'image/svg+xml' },
        ],
      },
      workbox: {
        // HTML must NOT be precached — browser must always fetch it fresh so
        // new asset hashes are discovered after each deploy.
        globPatterns: ['**/*.{js,css,ico,png,svg,woff2}'],
        // Activate the new service worker immediately instead of waiting for
        // all tabs to close (prevents the "need incognito" symptom).
        skipWaiting: true,
        clientsClaim: true,
        runtimeCaching: [
          {
            urlPattern: /^https?:\/\/.*\/api\/(tournaments|players\/categories)/,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'api-cache',
              expiration: { maxEntries: 50, maxAgeSeconds: 60 * 60 },
            },
          },
        ],
      },
    }),
  ],
  server: {
    host: '0.0.0.0',
    port: 5173,
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
    allowedHosts,
  },
});
