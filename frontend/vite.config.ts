import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'url';

// The backend the dev server proxies to; API_TARGET points it at another one (e.g. a scratch copy on :8001).
const API = process.env.API_TARGET ?? 'http://localhost:8000';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': API,
      '/sops': {
        target: API,
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html';
          }
        },
      },
      '/documents': API,
      '/templates': {
        target: API,
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html';
          }
        },
      },
      '/jobs': API,
      '/review': {
        target: API,
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html';
          }
        },
      },
      // `/migrations` is also an app page (the v2 jobs live under /api/v1/migrations)
      '/migrations': {
        target: API,
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html';
          }
        },
      },
      '/issues': API,
      '/suggestions': API,
      '/reprocessing-requests': API,
      '/workflows': API,
      '/health': API,
    },
  },
});
