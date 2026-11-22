// The app's TanStack Query client: retry rules and the 401 redirect.
import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'

import { isApiError } from '@/api/errors'

const MAX_RETRIES = 2

declare module '@tanstack/react-query' {
  interface Register {
    queryMeta: { allowUnauthorized?: boolean }
    mutationMeta: { allowUnauthorized?: boolean }
  }
}

/** Retry network and server errors; never retry what the server refused. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= MAX_RETRIES) {
    return false
  }
  return (
    isApiError(error, 'network') ||
    isApiError(error, 'internal') ||
    isApiError(error, 'unavailable')
  )
}

/**
 * @param onUnauthorized called when a request comes back 401, unless the
 *   query or mutation opts out with `meta: { allowUnauthorized: true }`.
 */
export function createQueryClient(onUnauthorized: () => void): QueryClient {
  const handle = (error: unknown, meta: { allowUnauthorized?: boolean } | undefined) => {
    if (isApiError(error, 'unauthorized') && !meta?.allowUnauthorized) {
      onUnauthorized()
    }
  }
  return new QueryClient({
    queryCache: new QueryCache({ onError: (error, query) => handle(error, query.meta) }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) => handle(error, mutation.meta),
    }),
    defaultOptions: {
      queries: {
        retry: shouldRetry,
        refetchOnWindowFocus: false,
        staleTime: 15_000,
      },
      mutations: { retry: false },
    },
  })
}
