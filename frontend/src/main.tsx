import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'
import './styles/index.css'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { createAppRouter } from './router'

const queryClient = new QueryClient()
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
