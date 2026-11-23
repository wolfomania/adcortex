import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'
import './styles/index.css'

import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { queryKeys } from './api/queries'
import { isPublicPath } from './app/auth'
import { createQueryClient } from './app/queryClient'
import { createAppRouter } from './router'

async function start(): Promise<void> {
  // `pnpm dev` runs on the mock backend; `pnpm dev:backend` and builds use the real API.
  if (import.meta.env.DEV && import.meta.env.MODE !== 'backend') {
    const { startMockBackend } = await import('./mocks/browser')
    await startMockBackend()
  }

  const queryClient = createQueryClient(() => {
    // The session ended: forget it and ask for the password again.
    const { pathname, href } = router.state.location
    if (isPublicPath(pathname)) {
      return
    }
    queryClient.removeQueries({ queryKey: queryKeys.config })
    void router.navigate({ to: '/login', search: { next: href }, replace: true })
  })
  const router = createAppRouter(queryClient)

  const container = document.getElementById('root')
  if (!container) {
    throw new Error('Missing #root element')
  }
  createRoot(container).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>,
  )
}

void start()
