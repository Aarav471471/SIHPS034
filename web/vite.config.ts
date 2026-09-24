import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import path from 'node:path';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg'],
      manifest: {
        name: 'MetriX — Legal Metrology Compliance',
        short_name: 'MetriX',
        description:
          'AI-powered Legal Metrology compliance for packaged commodities. Scan before you buy, report violations, and inspect in the field.',
        theme_color: '#0f3d6e',
        background_color: '#f8fafc',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        // The app shell is cached so an officer can open the capture screen
        // with no signal. API responses are deliberately NOT cached by default:
        // a stale compliance score or MRP could mislead an enforcement
        // decision. Only genuinely static reference data is cached, and the
        // consumer scan cache lives in IndexedDB where its age is checked.
        runtimeCaching: [
          {
            urlPattern: /\/api\/(categories|policy\/rules)/,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'metrix-reference',
              expiration: { maxEntries: 40, maxAgeSeconds: 60 * 60 * 24 },
            },
          },
          {
            urlPattern: /\/storage\/.*\.(png|jpg|jpeg|webp)$/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'metrix-evidence',
              expiration: { maxEntries: 300, maxAgeSeconds: 60 * 60 * 24 * 14 },
            },
          },
        ],
        navigateFallbackDenylist: [/^\/api/, /^\/storage/, /^\/docs/],
      },
      devOptions: { enabled: false },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      '@shared': path.resolve(__dirname, '../packages/shared/src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Keep the big visualisation libraries out of the entry chunk. They are
        // each used by exactly one role, and loading them for everyone slows
        // the screens that matter most in the field.
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts'],
          maps: ['leaflet', 'react-leaflet'],
          query: ['@tanstack/react-query'],
        },
      },
    },
    chunkSizeWarningLimit: 600,
  },
  server: {
    port: 5173,
    proxy: {
      // `ws: true` is required for /api/ws/sessions/*: without it the dev
      // server answers the upgrade request itself instead of forwarding it, so
      // the pipeline socket never connects and the session page sits on
      // "Reconnecting…" while the run completes invisibly behind it.
      '/api': { target: 'http://localhost:8000', changeOrigin: true, ws: true },
      '/storage': { target: 'http://localhost:8000', changeOrigin: true },
      '/health': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
});
