// The API client against the mock backend (src/mocks), route by route.
import { describe, expect, it } from 'vitest'

import { clock, mockDb, resetMockBackend } from '@/test/server'

import { api, mediaUrls, sourceKey, sourcePath, toFormData } from './endpoints'
import { ApiRequestError } from './errors'

const ID_PATTERN = /^\d{8}-\d{6}-[0-9a-f]{6}$/

async function seededIds() {
  const { items } = await api.history({ limit: 100 })
  const byName = (name: string) => items.find((item) => item.meta.name === name)!.meta.id
  return {
    lumen30: byName('Lumen launch: 30s master'),
    lumen15: byName('Lumen launch: 15s cut-down'),
    radio: byName('Lumen radio spot'),
    broken: byName('Holiday teaser'),
    script: byName('Lumen script: draft 2'),
  }
}

function videoFile(name = 'spot.mp4', size = 1024): File {
  return new File([new Uint8Array(size)], name, { type: 'video/mp4' })
}

describe('toFormData', () => {
  it('writes only the fields that are set, trimming the name', () => {
    const data = toFormData({
      kind: 'video',
      file: videoFile(),
      name: '  Spring spot ',
      language: 'auto',
    })
    expect(data.get('kind')).toBe('video')
    expect((data.get('file') as File).name).toBe('spot.mp4')
    expect(data.get('name')).toBe('Spring spot')
    expect(data.get('language')).toBe('auto')
    expect(data.has('script')).toBe(false)
  })

  it('drops a blank name and keeps the script', () => {
    const data = toFormData({ kind: 'text', script: 'Hello there, lamp.', name: '   ' })
    expect(data.has('name')).toBe(false)
    expect(data.get('script')).toBe('Hello there, lamp.')
  })
})

describe('media paths', () => {
  it('builds owner and share-link URLs', () => {
    expect(sourcePath({ kind: 'analysis', id: 'a b' })).toBe('/analyses/a%20b')
    expect(mediaUrls.media({ kind: 'shared', token: 'tok' })).toBe('/api/shared/tok/media')
    expect(mediaUrls.strip({ kind: 'analysis', id: 'x' })).toBe('/api/analyses/x/strip')
    expect(mediaUrls.keyframe({ kind: 'analysis', id: 'x' }, 2)).toBe('/api/analyses/x/keyframes/2')
    expect(sourceKey({ kind: 'analysis', id: 'x' })).toBe('a:x')
    expect(sourceKey({ kind: 'shared', token: 'y' })).toBe('s:y')
  })
})

describe('config and auth', () => {
  it('reports the backend settings', async () => {
    const config = await api.config()
    expect(config.brain_backend).toBe('tribe')
    expect(config.password_required).toBe(false)
    expect(config.languages.find((l) => l.code === 'en')?.full_support).toBe(true)
    expect(config.limits.max_upload_mb).toBe(500)
  })

  it('gates private routes behind the password', async () => {
    resetMockBackend({ password: true })
    await expect(api.history()).rejects.toMatchObject({ code: 'unauthorized', status: 401 })
    expect((await api.config()).authenticated).toBe(false)

    await expect(api.login('nope')).rejects.toMatchObject({ code: 'unauthorized' })
    await expect(api.login('lumen')).resolves.toEqual({ authenticated: true })
    expect((await api.history()).items.length).toBeGreaterThan(0)

    await api.logout()
    await expect(api.history()).rejects.toBeInstanceOf(ApiRequestError)
  })

  it('limits login attempts to five a minute', async () => {
    resetMockBackend({ password: true })
    for (let i = 0; i < 5; i += 1) {
      await expect(api.login('wrong')).rejects.toMatchObject({ code: 'unauthorized' })
    }
    await expect(api.login('lumen')).rejects.toMatchObject({ code: 'rate_limited', status: 429 })
    clock.advance(61_000)
    await expect(api.login('lumen')).resolves.toEqual({ authenticated: true })
  })
})

describe('history', () => {
  it('lists newest first and pages with next_before', async () => {
    const first = await api.history({ limit: 5 })
    expect(first.items).toHaveLength(5)
    expect(first.items.every((item) => ID_PATTERN.test(item.meta.id))).toBe(true)
    const ids = first.items.map((item) => item.meta.id)
    expect([...ids].sort().reverse()).toEqual(ids)
    expect(first.items.every((item) => item.progress === null)).toBe(true)
    expect(first.nextBefore).toBe(ids.at(-1))

    const second = await api.history({ limit: 100, before: first.nextBefore })
    expect(second.nextBefore).toBeNull()
    expect(second.items.every((item) => item.meta.id < ids.at(-1)!)).toBe(true)
  })

  it('rejects a limit outside 1-100', async () => {
    await expect(api.history({ limit: 101 })).rejects.toMatchObject({ code: 'invalid_input' })
  })

  it('starts empty in the empty scenario', async () => {
    resetMockBackend({ empty: true })
    await expect(api.history()).resolves.toEqual({ items: [], nextBefore: null })
  })
})

describe('analysis detail', () => {
  it('returns the result, the report, and the library rank', async () => {
    const { lumen30 } = await seededIds()
    const detail = await api.analysis(lumen30)
    expect(detail.analysis.state.status).toBe('completed')
    expect(detail.analysis.state.summary?.headline).toBe(detail.report?.report.headline)
    expect(detail.result?.systems).toHaveLength(10)
    expect(detail.result?.scores.response_index).toBe(57.1)
    expect(detail.result?.systems.every((s) => typeof s.library_percentile === 'number')).toBe(true)
    expect(detail.report?.model).toBe('google:gemini-4-hydrogen')
  })

  it('carries the reused prediction and failed report states', async () => {
    const { items } = await api.history({ limit: 100 })
    const rerun = items.find((item) => item.meta.name.endsWith('(re-run)'))!
    const { lumen30, radio } = await seededIds()
    expect(rerun.state.reused_from).toBe(lumen30)
    const detail = await api.analysis(radio)
    expect(detail.report).toBeNull()
    expect(detail.analysis.state.llm).toMatchObject({ status: 'failed' })
    expect(detail.result?.baseline).toBeNull()
    expect(detail.result?.scores.response_index).toBeNull()
  })

  it('answers 404 for an unknown id', async () => {
    await expect(api.analysis('20260101-000000-abcdef')).rejects.toMatchObject({
      code: 'not_found',
      status: 404,
    })
  })
})

describe('upload and processing', () => {
  it('moves through the pipeline and completes with a report', async () => {
    const created = await api.create({
      kind: 'video',
      file: videoFile('launch.mp4'),
      language: 'auto',
    })
    expect(created.state.status).toBe('queued')
    expect(created.meta.name).toBe('launch')

    clock.advance(9_000)
    const running = await api.status(created.meta.id)
    expect(['waiting_for_gpu', 'predicting']).toContain(running.state.status)
    expect(running.progress?.fraction).toBeGreaterThan(0.1)
    expect(running.progress?.message).toBeTruthy()

    clock.advance(60_000)
    const detail = await api.analysis(created.meta.id)
    expect(detail.analysis.state.status).toBe('completed')
    expect(detail.analysis.progress).toBeNull()
    expect(detail.report?.report.headline).toContain('presenter')
  })

  it('validates the form like the backend', async () => {
    await expect(api.create({ kind: 'text', script: 'Too short' })).rejects.toMatchObject({
      code: 'invalid_input',
      status: 422,
    })
    await expect(
      api.create({
        kind: 'video',
        file: new File([new Uint8Array(4)], 'a.m4a', { type: 'audio/mp4' }),
      }),
    ).rejects.toMatchObject({ code: 'invalid_input' })
    await expect(
      api.create({ kind: 'video', file: videoFile('too-long.mp4') }),
    ).rejects.toMatchObject({
      message: expect.stringContaining('180 s'),
    })
    await expect(
      api.create({ kind: 'audio', file: videoFile('x.mp4'), language: 'xx' }),
    ).rejects.toMatchObject({
      message: "Unsupported language 'xx'.",
    })
  })

  it('reports upload progress', async () => {
    const fractions: number[] = []
    await api.create(
      { kind: 'text', script: 'Introducing Lumen, the lamp that learns your rhythm.' },
      { onProgress: (fraction) => fractions.push(fraction) },
    )
    expect(fractions.every((f) => f >= 0 && f <= 1)).toBe(true)
  })

  it('fails while predicting in the fail scenario, then retries', async () => {
    resetMockBackend({ failUploads: true })
    const created = await api.create({ kind: 'audio', file: videoFile('radio.m4a') })
    clock.advance(30_000)
    const failed = await api.status(created.meta.id)
    expect(failed.state.status).toBe('failed')
    expect(failed.state.error).toContain('out of memory')
    expect(failed.state.media?.has_video).toBe(false)

    await expect(api.retry(created.meta.id)).resolves.toMatchObject({ state: { status: 'queued' } })
    await expect(api.retry(created.meta.id)).rejects.toMatchObject({
      code: 'conflict',
      status: 409,
    })
  })

  it('skips the report step without a model', async () => {
    resetMockBackend({ llm: false })
    const created = await api.create({ kind: 'video', file: videoFile() })
    clock.advance(60_000)
    const detail = await api.analysis(created.meta.id)
    expect(detail.analysis.state.llm).toMatchObject({ status: 'skipped', model: null })
    expect(detail.report).toBeNull()
    await expect(api.regenerateReport(created.meta.id)).rejects.toMatchObject({
      code: 'unavailable',
    })
  })
})

describe('changes', () => {
  it('renames, regenerates the report, and deletes', async () => {
    const { radio } = await seededIds()
    await expect(api.rename(radio, '  Radio v2 ')).resolves.toMatchObject({
      meta: { name: 'Radio v2' },
    })
    await expect(api.rename(radio, ' ')).rejects.toMatchObject({ code: 'invalid_input' })

    const writing = await api.regenerateReport(radio)
    expect(writing.state.status).toBe('interpreting')
    expect((await api.analysis(radio)).result).not.toBeNull()
    clock.advance(10_000)
    const detail = await api.analysis(radio)
    expect(detail.report?.report.headline).toContain('opening question')

    await expect(api.remove(radio)).resolves.toBeNull()
    await expect(api.status(radio)).rejects.toMatchObject({ code: 'not_found' })
  })
})

describe('sharing', () => {
  it('serves a read-only copy until the analysis is deleted', async () => {
    const { lumen15 } = await seededIds()
    const link = await api.share(lumen15)
    expect(link.path).toBe(`/s/${link.token}`)
    expect(link.token).toMatch(/^[\w-]+\.[a-z0-9]+$/)

    resetMockBackend({ password: true })
    await expect(api.shared(link.token)).rejects.toMatchObject({ code: 'not_found' })
  })

  it('works without logging in', async () => {
    const { lumen15 } = await seededIds()
    const link = await api.share(lumen15)
    const shared = await api.shared(link.token)
    expect(shared.analysis.meta.id).toBe(lumen15)
    const frames = await api.frames({ kind: 'shared', token: link.token })
    expect(frames.byteLength).toBe(15 * 20484)

    await api.remove(lumen15)
    await expect(api.shared(link.token)).rejects.toMatchObject({ code: 'not_found' })
  })

  it('refuses to share an unfinished analysis', async () => {
    const { broken } = await seededIds()
    await expect(api.share(broken)).rejects.toMatchObject({ code: 'conflict' })
  })
})

describe('comparison', () => {
  it('runs, then returns the written comparison', async () => {
    const { lumen30, lumen15 } = await seededIds()
    await expect(api.comparison(lumen30, lumen15)).resolves.toMatchObject({ status: 'none' })
    await expect(api.compare(lumen30, lumen15)).resolves.toMatchObject({ status: 'running' })
    clock.advance(7_000)
    const done = await api.comparison(lumen30, lumen15)
    expect(done.status).toBe('completed')
    expect(done.comparison?.report.headline).toContain('cut-down')
    await expect(api.compare(lumen30, lumen15)).resolves.toMatchObject({ status: 'completed' })
  })

  it('writes a templated comparison for other pairs', async () => {
    const { lumen15, script } = await seededIds()
    await api.compare(script, lumen15)
    clock.advance(7_000)
    const done = await api.comparison(script, lumen15)
    expect(done.comparison?.report.a_strengths.length).toBeGreaterThan(0)
  })

  it('refuses unfinished analyses, missing models, and the same analysis twice', async () => {
    const { lumen30, broken } = await seededIds()
    await expect(api.compare(lumen30, broken)).rejects.toMatchObject({ code: 'conflict' })
    await expect(api.compare(lumen30, lumen30)).rejects.toMatchObject({ code: 'invalid_input' })
    resetMockBackend({ llm: false })
    const ids = await seededIds()
    await expect(api.compare(ids.lumen30, ids.lumen15)).rejects.toMatchObject({
      code: 'unavailable',
      status: 503,
    })
  })

  it('fails in the comparefail scenario', async () => {
    resetMockBackend({ failComparison: true })
    const { lumen30, lumen15 } = await seededIds()
    await api.compare(lumen30, lumen15)
    clock.advance(7_000)
    await expect(api.comparison(lumen30, lumen15)).resolves.toMatchObject({
      status: 'failed',
      error: expect.stringContaining('invalid comparison'),
    })
  })
})

describe('warmup and binary data', () => {
  it('starts the GPU once and reports it warm afterwards', async () => {
    await expect(api.warmup()).resolves.toEqual({ warming: true })
    await expect(api.warmup()).resolves.toEqual({ warming: true })
    clock.advance(5_000)
    await expect(api.warmup()).resolves.toEqual({ warming: false })
    clock.advance(300_000)
    await expect(api.warmup()).resolves.toEqual({ warming: true })
  })

  it('downloads brain frames as bytes around the average', async () => {
    const { lumen30 } = await seededIds()
    const buffer = await api.frames({ kind: 'analysis', id: lumen30 })
    const bytes = new Uint8Array(buffer)
    expect(bytes.length).toBe(30 * 20484)
    const average = bytes.reduce((sum, b) => sum + b, 0) / bytes.length
    expect(average).toBeGreaterThan(100)
    expect(average).toBeLessThan(156)
  })

  it('reports binary errors as envelopes', async () => {
    const { broken } = await seededIds()
    await expect(api.frames({ kind: 'analysis', id: broken })).rejects.toMatchObject({
      code: 'not_found',
    })
    expect(mockDb().scenario.latencyMs).toBe(0)
  })
})
