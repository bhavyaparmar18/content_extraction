import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'url';

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
      '/api': 'http://localhost:8000',
      '/sops': {
        target: 'http://localhost:8000',
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html';
          }
        },
      },
      '/documents': 'http://localhost:8000',
      '/jobs': 'http://localhost:8000',
      '/review': {
        target: 'http://localhost:8000',
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html';
          }
        },
      },
      '/migrations': 'http://localhost:8000',
      '/translations': 'http://localhost:8000',
      '/issues': 'http://localhost:8000',
      '/suggestions': 'http://localhost:8000',
      '/reprocessing-requests': 'http://localhost:8000',
      '/workflows': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
});
