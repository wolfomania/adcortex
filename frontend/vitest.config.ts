import { fileURLToPath, URL } from 'node:url'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  test: {
    environment: 'jsdom',
    // The mock backend synthesizes brain frames on the CPU; allow for slow runners.
    testTimeout: 15_000,
    setupFiles: ['src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}', 'scripts/**/*.test.mjs'],
    restoreMocks: true,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/test/**',
        // Generated code: route tree, API types, and shadcn/ui primitives
        // (vendored from the shadcn registry).
        'src/routeTree.gen.ts',
        'src/api/schema.ts',
        'src/components/ui/**',
        // Development fixtures served by Mock Service Worker.
        'src/mocks/browser.ts',
        // Entry point and WebGL scene graph; jsdom has no WebGL context.
        'src/main.tsx',
        'src/features/brain/BrainView.tsx',
        'src/vite-env.d.ts',
      ],
      reporter: ['text-summary', 'text', 'html'],
      thresholds: { statements: 80, branches: 75, functions: 80, lines: 80 },
    },
  },
})
