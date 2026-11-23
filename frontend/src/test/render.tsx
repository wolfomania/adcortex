// Renders the whole app at a path, on the mock backend (see server.ts).
import { QueryClientProvider } from '@tanstack/react-query'
import { createMemoryHistory, RouterProvider } from '@tanstack/react-router'
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { createQueryClient } from '@/app/queryClient'
import { createAppRouter } from '@/router'

export function renderApp(path: string) {
  const queryClient = createQueryClient(() => {
    void router.navigate({ to: '/login', search: { next: router.state.location.href } })
  })
  queryClient.setDefaultOptions({
    ...queryClient.getDefaultOptions(),
    queries: { ...queryClient.getDefaultOptions().queries, retry: false },
  })
  const router = createAppRouter(queryClient, createMemoryHistory({ initialEntries: [path] }))
  const user = userEvent.setup()
  const view = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { ...view, router, queryClient, user }
}
