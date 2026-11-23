import { describe, expect, it, vi } from 'vitest'

import { ApiRequestError } from '@/api/errors'

import { createQueryClient, shouldRetry } from './queryClient'

const error = (code: ConstructorParameters<typeof ApiRequestError>[0]) =>
  new ApiRequestError(code, 'Nope.', 0)

describe('the query client', () => {
  it('retries outages a few times, and never refusals', () => {
    expect(shouldRetry(0, error('network'))).toBe(true)
    expect(shouldRetry(1, error('unavailable'))).toBe(true)
    expect(shouldRetry(2, error('internal'))).toBe(false)
    expect(shouldRetry(0, error('not_found'))).toBe(false)
    expect(shouldRetry(0, new Error('boom'))).toBe(false)
  })

  it('reports lost sessions unless the request expects them', async () => {
    const onUnauthorized = vi.fn()
    const client = createQueryClient(onUnauthorized)
    const refuse = () => Promise.reject(error('unauthorized'))

    await client.fetchQuery({ queryKey: ['a'], queryFn: refuse, retry: false }).catch(() => null)
    await client
      .fetchQuery({
        queryKey: ['b'],
        queryFn: refuse,
        retry: false,
        meta: { allowUnauthorized: true },
      })
      .catch(() => null)
    await client
      .getMutationCache()
      .build(client, { mutationFn: refuse })
      .execute(undefined)
      .catch(() => null)

    expect(onUnauthorized).toHaveBeenCalledTimes(2)
  })
})
