import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/endpoints'

/** Re-check a warming worker this often; stop once it is warm. */
const RECHECK_MS = 10_000
/** A warm worker stays warm for minutes; do not ask again sooner. */
const FRESH_MS = 60_000

export type GpuState = 'unknown' | 'warming' | 'ready'

/**
 * Start the GPU worker while the person picks a file (POST /api/warmup), so
 * the analysis does not wait for a cold start.
 */
export function useWarmup(): GpuState {
  const { data } = useQuery({
    queryKey: ['warmup'],
    queryFn: api.warmup,
    staleTime: FRESH_MS,
    retry: false,
    refetchOnWindowFocus: false,
    refetchInterval: (query) => (query.state.data?.warming ? RECHECK_MS : false),
    meta: { allowUnauthorized: true },
  })
  if (!data) {
    return 'unknown'
  }
  return data.warming ? 'warming' : 'ready'
}
