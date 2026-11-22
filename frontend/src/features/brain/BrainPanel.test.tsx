import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { useEffect } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { Playback, PlaybackContext } from '@/features/results/playback'
import { mockDb, server } from '@/test/server'

import { N_VERTICES } from './assets'
import { BrainPanel } from './BrainPanel'
import type { BrainViewProps } from './BrainView'

vi.mock('./webgl', () => ({ supportsWebGL: () => true }))
// The scene itself needs WebGL; this stand-in points at the first cortex vertex.
vi.mock('./BrainView', () => ({
  default: function FakeBrainView({ assets, surface, view, onHover }: BrainViewProps) {
    useEffect(() => {
      onHover?.(assets.mesh.parcel.findIndex((parcel) => parcel !== 0))
    }, [assets, onHover])
    return <p>{`brain: ${surface}, ${view}`}</p>
  },
}))

function renderPanel() {
  const record = mockDb()
    .state()
    .records.find((item) => item.name === 'Lumen launch: 30s master')
  const result = record && mockDb().detail(record.id).result
  if (!record || !result?.frames) {
    throw new Error('Missing the seeded analysis')
  }
  // Flat maps (every vertex at the reference average): the mock's synthesized
  // maps take seconds under coverage, and this test is about loading, not values.
  const flat = new Uint8Array(result.frames.n_frames * N_VERTICES).fill(128)
  server.use(http.get('*/api/analyses/:id/frames', () => HttpResponse.arrayBuffer(flat.buffer)))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <PlaybackContext.Provider value={new Playback(result.duration_s)}>
        <BrainPanel result={result} source={{ kind: 'analysis', id: record.id }} />
      </PlaybackContext.Provider>
    </QueryClientProvider>,
  )
}

describe('BrainPanel', () => {
  it('loads the cortex and the brain maps, and names the region under the pointer', async () => {
    const user = userEvent.setup()
    renderPanel()

    expect(await screen.findByText('brain: inflated, left', {}, { timeout: 10_000 })).toBeVisible()
    expect(await screen.findByText(/\(left\)/, {}, { timeout: 10_000 })).toBeVisible()

    await user.click(screen.getByRole('radio', { name: 'Folded' }))
    await user.click(screen.getByRole('radio', { name: 'Top' }))
    expect(await screen.findByText('brain: pial, top')).toBeVisible()
  })
})
