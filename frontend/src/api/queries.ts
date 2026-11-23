// TanStack Query keys and options for every API read.
import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query'

import { isTerminal, POLL_INTERVAL_MS } from '@/features/analysis/status'

import { api, sourceKey } from './endpoints'
import type { Analysis, ComparisonState, MediaSource } from './types'

export const queryKeys = {
  config: ['config'] as const,
  analyses: ['analyses'] as const,
  history: ['analyses', 'history'] as const,
  analysis: (id: string) => ['analyses', 'detail', id] as const,
  status: (id: string) => ['analyses', 'status', id] as const,
  shared: (token: string) => ['shared', token] as const,
  comparison: (aId: string, bId: string) => ['comparison', aId, bId] as const,
  frames: (source: MediaSource) => ['frames', sourceKey(source)] as const,
}

export function configQuery() {
  return queryOptions({
    queryKey: queryKeys.config,
    queryFn: api.config,
    staleTime: 5 * 60_000,
  })
}

/** Should a status poll continue after this response? */
export function shouldPollStatus(analysis: Analysis | undefined): boolean {
  return analysis === undefined || !isTerminal(analysis.state.status)
}

export function statusQuery(id: string) {
  return queryOptions({
    queryKey: queryKeys.status(id),
    queryFn: () => api.status(id),
    refetchInterval: (query) => (shouldPollStatus(query.state.data) ? POLL_INTERVAL_MS : false),
    refetchIntervalInBackground: true,
  })
}

export function analysisQuery(id: string) {
  return queryOptions({
    queryKey: queryKeys.analysis(id),
    queryFn: () => api.analysis(id),
  })
}

export function sharedQuery(token: string) {
  return queryOptions({
    queryKey: queryKeys.shared(token),
    queryFn: () => api.shared(token),
    retry: false,
  })
}

export const HISTORY_PAGE_SIZE = 30

export function historyQuery() {
  return infiniteQueryOptions({
    queryKey: queryKeys.history,
    queryFn: ({ pageParam }) => api.history({ limit: HISTORY_PAGE_SIZE, before: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.nextBefore,
  })
}

/** Should a comparison poll continue after this response? */
export function shouldPollComparison(state: ComparisonState | undefined): boolean {
  return state?.status === 'running'
}

export function comparisonQuery(aId: string, bId: string) {
  return queryOptions({
    queryKey: queryKeys.comparison(aId, bId),
    queryFn: () => api.comparison(aId, bId),
    refetchInterval: (query) => (shouldPollComparison(query.state.data) ? POLL_INTERVAL_MS : false),
    retry: false,
  })
}

export function framesQuery(source: MediaSource) {
  return queryOptions({
    queryKey: queryKeys.frames(source),
    queryFn: ({ signal }) => api.frames(source, signal),
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: 10 * 60_000,
  })
}
