// The pages, end to end on the mock backend.
import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'

import { MOCK_PASSWORD } from '@/mocks/scenario'
import { renderApp } from '@/test/render'
import { clock, mockDb, resetMockBackend, server } from '@/test/server'

// jsdom has no WebGL; the brain panel shows its fallback.
vi.mock('@/features/brain/webgl', () => ({ supportsWebGL: () => false }))
// jsdom cannot decode media; every clip is 12 seconds long.
vi.mock('@/features/upload/probe', () => ({ probeDuration: () => Promise.resolve(12) }))

/** Long enough for a status or comparison poll (1.5 s) to land. */
const POLL = { timeout: 4000 }

function idOf(name: string): string {
  const record = mockDb()
    .state()
    .records.find((item) => item.name === name)
  if (!record) {
    throw new Error(`No seeded analysis named ${name}`)
  }
  return record.id
}

describe('the app', () => {
  it('opens on the upload form', async () => {
    renderApp('/')

    expect(await screen.findByRole('heading', { name: /how would a brain respond/i })).toBeVisible()
    expect(screen.getByRole('form', { name: 'New analysis' })).toBeVisible()
  })

  it('shows a completed analysis: scores, report, systems, and transcript', async () => {
    renderApp(`/a/${idOf('Lumen launch: 30s master')}`)

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Lumen launch: 30s master' }),
    ).toBeVisible()
    expect(screen.getByText('Response index')).toBeVisible()
    expect(screen.getByText(/^Written by /)).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Brain systems' })).toBeVisible()
    expect(screen.getByRole('slider', { name: 'Playhead' })).toBeVisible()
    expect(screen.getByText(/needs WebGL/)).toBeVisible()
  })

  it('retries a failed analysis and follows it to the results', async () => {
    const { user } = renderApp(`/a/${idOf('Holiday teaser')}`)

    await user.click(await screen.findByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('list', { name: 'Stages' })).toBeVisible()
    clock.advance(30 * 60_000)

    expect(await screen.findByText('Response index', {}, POLL)).toBeVisible()
    expect(screen.queryByRole('list', { name: 'Stages' })).toBeNull()
  })

  it('picks two analyses in History and compares them', async () => {
    const { user } = renderApp('/history')

    await user.click(
      await screen.findByRole('checkbox', { name: 'Select “Lumen launch: 30s master” to compare' }),
    )
    await user.click(
      screen.getByRole('checkbox', { name: 'Select “Lumen launch: 15s cut-down” to compare' }),
    )
    await user.click(screen.getByRole('button', { name: /^Compare/ }))

    expect(await screen.findByRole('heading', { level: 1, name: 'Comparison' })).toBeVisible()
    const scores = screen.getByRole('table', { name: 'Scores' })
    expect(within(scores).getByRole('rowheader', { name: 'Hook' })).toBeVisible()

    await user.click(await screen.findByRole('button', { name: 'Write the comparison' }))
    clock.advance(5 * 60_000)
    expect(await screen.findByText(/^Written by /, {}, POLL)).toBeVisible()
  })

  it('renames and deletes from History', async () => {
    const { user } = renderApp('/history')

    await user.click(await screen.findByRole('button', { name: 'Actions for “Holiday teaser”' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Rename' }))
    const name = await screen.findByRole('textbox', { name: 'Name' })
    await user.clear(name)
    await user.type(name, 'Holiday teaser, final{Enter}')
    expect(await screen.findByRole('link', { name: 'Holiday teaser, final' })).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Actions for “Holiday teaser, final”' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Delete' }))
    await user.click(await screen.findByRole('button', { name: 'Delete' }))
    await waitFor(() => {
      expect(screen.queryByRole('link', { name: 'Holiday teaser, final' })).toBeNull()
    })
  })

  it('asks for the password, then opens the page that was asked for', async () => {
    resetMockBackend({ password: true })
    const { user } = renderApp('/history')

    const password = await screen.findByLabelText('Password')
    await user.type(password, 'wrong{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent('That password is not right.')
    await user.clear(password)
    await user.type(password, `${MOCK_PASSWORD}{Enter}`)

    expect(await screen.findByRole('heading', { level: 1, name: 'History' })).toBeVisible()
  })

  it('opens share links without a session, read-only', async () => {
    resetMockBackend({ password: true })
    const link = mockDb().share(idOf('Lumen launch: 30s master'))
    renderApp(link.path)

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Lumen launch: 30s master' }),
    ).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Share' })).toBeNull()
    expect(screen.queryByRole('button', { name: /Rewrite/ })).toBeNull()
  })

  it('uploads a script and follows its progress', async () => {
    const { user } = renderApp('/')

    await user.click(await screen.findByRole('tab', { name: 'Script' }))
    await user.type(
      screen.getByRole('textbox', { name: 'Script' }),
      'Meet Lumen, the lamp that learns your evenings and dims itself when the film starts.',
    )
    await user.click(screen.getByRole('button', { name: 'Analyze' }))

    expect(await screen.findByRole('list', { name: 'Stages' })).toBeVisible()
    expect(screen.getByRole('heading', { level: 1, name: /^Meet Lumen/ })).toBeVisible()
  })

  it('uploads a video file', async () => {
    const { user, container } = renderApp('/')
    await screen.findByRole('form', { name: 'New analysis' })
    const input = container.querySelector<HTMLInputElement>('input[type=file]')
    if (!input) {
      throw new Error('No file input')
    }

    await user.upload(
      input,
      new File([new Uint8Array(2048)], 'spring_spot.mp4', { type: 'video/mp4' }),
    )
    await user.click(await screen.findByRole('button', { name: 'Analyze' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'spring_spot' })).toBeVisible()
  })

  it('explains when an analysis does not exist', async () => {
    renderApp('/a/20990101-000000-abcdef')

    expect(await screen.findByRole('heading', { name: 'Analysis not found' })).toBeVisible()
  })

  it('shares a completed analysis and exports its data', async () => {
    const created = vi.fn((_: Blob) => 'blob:export')
    Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const { user } = renderApp(`/a/${idOf('Lumen launch: 30s master')}`)

    await user.click(await screen.findByRole('button', { name: 'Share' }))
    const link = await screen.findByRole('textbox', { name: 'Share link' })
    await waitFor(() => {
      expect((link as HTMLInputElement).value).toMatch(/\/s\/.+/)
    })
    await user.click(screen.getByRole('button', { name: 'Copy' }))
    expect(await screen.findByText('Link copied')).toBeVisible()
    await user.keyboard('{Escape}')

    await user.click(screen.getByRole('button', { name: 'Export' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Download the data (JSON)' }))
    expect(click).toHaveBeenCalledOnce()
    expect(created).toHaveBeenCalledOnce()

    // The standalone report carries the scene keyframes inline.
    server.use(
      http.get('*/keyframes/:index', () =>
        HttpResponse.arrayBuffer(new Uint8Array([0xff, 0xd8, 0xff]).buffer, {
          headers: { 'Content-Type': 'image/jpeg' },
        }),
      ),
    )
    await user.click(screen.getByRole('button', { name: 'Export' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Download the report (HTML)' }))
    await waitFor(() => {
      expect(created).toHaveBeenCalledTimes(2)
    })
    const report = created.mock.calls[1]?.[0]
    expect(report?.type).toBe('text/html')
    const html = (await report?.text()) ?? ''
    expect(html).toContain('<h1>Lumen launch: 30s master</h1>')
    expect(html).toContain('<img src="data:image/jpeg;base64,')
  })

  it('shows audio and script analyses, and reports that could not be written', async () => {
    const radio = renderApp(`/a/${idOf('Lumen radio spot')}`)
    expect(await screen.findByRole('heading', { name: 'The audio' })).toBeVisible()
    expect(screen.getByText(/Writing the report failed/)).toBeVisible()
    // The radio fixture was measured without a reference library, so the
    // z-scores compare the clip with itself and there are no reference ranks.
    expect(screen.getByText(/No reference library is installed/)).toBeVisible()
    expect(screen.getByText("Above this clip's average")).toBeVisible()
    expect(screen.getByText(/against this clip's own average/)).toBeVisible()
    expect(screen.queryByText(/vs reference/)).toBeNull()
    // Each system's mean is then zero by construction, so its peak stands in.
    expect(screen.getByText(/shows each system's strongest second/)).toBeVisible()
    expect(screen.getAllByText(/^peak [+−±]\d/).length).toBeGreaterThan(0)
    radio.unmount()

    const script = renderApp(`/a/${idOf('Lumen script: draft 2')}`)
    expect(await screen.findByRole('heading', { name: 'The script, read aloud' })).toBeVisible()
    script.unmount()

    renderApp(`/a/${idOf('Lumen 15s: Spanish dub')}`)
    expect(await screen.findByText(/metrics only/)).toBeVisible()
  })

  it('explains share links that no longer work', async () => {
    renderApp('/s/expired-token')

    expect(await screen.findByRole('heading', { name: 'This link no longer works' })).toBeVisible()
  })

  it('invites the first upload when History is empty', async () => {
    resetMockBackend({ empty: true })
    renderApp('/history')

    expect(await screen.findByRole('heading', { name: 'No analyses yet' })).toBeVisible()
  })
})
