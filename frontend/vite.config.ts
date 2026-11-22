import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import { tanstackRouter } from '@tanstack/router-plugin/vite'
import react from '@vitejs/plugin-react'
import { msw } from 'msw/vite'
import { defineConfig } from 'vite'

// `pnpm dev` serves the app on Mock Service Worker fixtures.
// `pnpm dev:backend` (mode "backend") proxies /api to a local backend instead.
export default defineConfig({
  plugins: [
    tanstackRouter({ target: 'react', autoCodeSplitting: true }),
    react(),
    tailwindcss(),
    // Serves the worker script in development only; production builds never
    // import the mocks, so the worker is not emitted.
    msw(),
  ],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    // scripts/check-size.mjs reads the manifest to measure the upload route.
    manifest: true,
    target: 'es2022',
    chunkSizeWarningLimit: 800,
  },
})
