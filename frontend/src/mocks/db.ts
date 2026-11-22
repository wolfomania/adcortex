// The mock backend: analyses that progress over time, reports, shares,
// comparisons, the GPU warm-up, and the optional password.
import type {
  Analysis,
  AnalysisDetail,
  AnalysisResult,
  AnalysisSummary,
  AppConfig,
  ComparisonState,
  LanguageInfo,
  SessionInfo,
  ShareLink,
  StoredReport,
  WarmupState,
} from '@/api/types'
import { loadBrainAssets } from '@/features/brain/assets'

import { comparisonOf } from './compare'
import { MOCK_LANGUAGES, MOCK_LIMITS } from './config'
import { CLIPS, type ClipId } from './fixtures/clips'
import { synthesizeFrames } from './fixtures/frames'
import { hashString } from './fixtures/math'
import { CLIP_REPORTS } from './fixtures/reports'
import { buildResult, type BuiltResult } from './fixtures/results'
import { UPLOAD_TWINS, type FixtureSpec } from './fixtures/seeds'
import type { Phase } from './progress'
import {
  analysisId,
  clipOf,
  hasMetrics,
  MOCK_MODEL,
  phaseOf,
  toAnalysis,
  type MockRecord,
} from './records'
import { MOCK_PASSWORD, type Scenario } from './scenario'
import { fakeSha256, type MockState } from './state'
import { defaultName, MockError, type ParsedUpload } from './upload'

/**
 * Synthesized brain frames, shared by every mock db: they depend only on the
 * fixture, and tests start a fresh db for each case.
 */
const synthesized = new Map<string, Promise<Uint8Array>>()

const MINUTE = 60_000
const SHARE_MS = 30 * 24 * 60 * MINUTE
const GPU_START_MS = 4200
const GPU_IDLE_MS = 240_000
const LOGIN_LIMIT = 5
const MIN_LIBRARY = 10

export const UPLOAD_FAILURE =
  'The GPU worker ran out of memory while predicting. Try a shorter clip, or try again in a few minutes.'

export interface MockDbOptions {
  scenario: Scenario
  state: MockState
  now?: () => number
  /** Called with the new state after every change. */
  onChange?: (state: MockState) => void
}

function clipFor(upload: ParsedUpload): ClipId {
  if (upload.kind === 'text') {
    return 'script-15s'
  }
  if (upload.kind === 'audio') {
    return 'radio-20s'
  }
  return /15/.test(upload.file?.name ?? '') ? 'lumen-15s' : 'lumen-30s'
}

function languageFor(requested: string, clipId: ClipId): LanguageInfo {
  const chosen = requested === 'auto' && CLIPS[clipId].kind === 'text' ? 'en' : requested
  const detected = chosen === 'auto' ? 'en' : chosen
  return { requested: chosen, detected, full_support: detected === 'en' }
}

function percentileOf(value: number, samples: readonly number[]): number | null {
  if (samples.length === 0) {
    return null
  }
  const below = samples.filter((s) => s < value).length
  const equal = samples.filter((s) => s === value).length
  return Math.round((1000 * (below + 0.5 * equal)) / samples.length) / 10
}

function base64url(text: string): string {
  return btoa(text).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

export type MockDb = ReturnType<typeof createMockDb>

export function createMockDb(options: MockDbOptions) {
  const { scenario, onChange } = options
  const now = options.now ?? Date.now
  let state = options.state
  const built = new Map<string, BuiltResult>()
  function commit(next: MockState): void {
    state = next
    onChange?.(state)
  }

  function find(id: string): MockRecord {
    const record = state.records.find((r) => r.id === id)
    if (!record) {
      throw new MockError('not_found', 'Analysis not found.')
    }
    return record
  }

  function updateRecord(id: string, change: (record: MockRecord) => MockRecord): MockRecord {
    const next = change(find(id))
    commit({ ...state, records: state.records.map((r) => (r.id === id ? next : r)) })
    return next
  }

  const fixtureKey = (record: MockRecord): string =>
    `${record.clipId}|${JSON.stringify(record.fixture)}`

  function builtFor(record: MockRecord): BuiltResult {
    const key = fixtureKey(record)
    const cached = built.get(key)
    if (cached) {
      return cached
    }
    const value = buildResult({
      clip: clipOf(record),
      ...record.fixture,
      language: record.language,
    })
    built.set(key, value)
    return value
  }

  const phase = (record: MockRecord): Phase => phaseOf(record, now(), scenario.speed)
  const isCompleted = (record: MockRecord): boolean => phase(record).status === 'completed'
  const nowIso = (): string => new Date(now()).toISOString()

  /** The result as this record sees it: its own language and library rank. */
  function resultFor(record: MockRecord): AnalysisResult {
    const base = builtFor(record)
    const others = state.records.filter((r) => r.id !== record.id && isCompleted(r))
    const means = others.map((r) => builtFor(r).summary.system_means ?? {})
    const systems = base.result.systems.map((s) => {
      const own = base.summary.system_means?.[s.id]
      const samples = means.flatMap((m) => (typeof m[s.id] === 'number' ? [m[s.id]!] : []))
      const ranked = s.applicable !== false && own !== undefined && samples.length >= MIN_LIBRARY
      return { ...s, library_percentile: ranked ? percentileOf(own, samples) : null }
    })
    return { ...base.result, systems, language: record.language }
  }

  function reportOf(record: MockRecord): StoredReport | null {
    if (!isCompleted(record) || record.llm.status !== 'ok') {
      return null
    }
    const clip = clipOf(record)
    return {
      created_at: new Date((record.job?.startedAt ?? record.createdAt) + 90_000).toISOString(),
      input_mode: clip.kind,
      model: MOCK_MODEL,
      report: CLIP_REPORTS[clip.id],
    }
  }

  function render(record: MockRecord, live: boolean): Analysis {
    const current = phase(record)
    const summary: AnalysisSummary | null = hasMetrics(record, current)
      ? { ...builtFor(record).summary, headline: reportOf(record)?.report.headline ?? null }
      : null
    return toAnalysis(record, { phase: current, summary, nowIso: nowIso(), live })
  }

  /** Start the GPU worker unless it is warm; returns whether a job must wait for it. */
  function claimGpu(): boolean {
    const t = now()
    const cold = t >= state.gpu.warmUntil
    const warmingUntil = cold ? t + GPU_START_MS / scenario.speed : state.gpu.warmingUntil
    commit({ ...state, gpu: { warmingUntil, warmUntil: t + GPU_IDLE_MS } })
    return t < warmingUntil
  }

  function startJob(record: MockRecord, reportOnly: boolean): MockRecord {
    return {
      ...record,
      job: {
        startedAt: now(),
        coldGpu: reportOnly ? false : claimGpu(),
        llm: scenario.llm,
        failAt: !reportOnly && scenario.failUploads ? 'predicting' : null,
        reportOnly,
      },
    }
  }

  function freshFixture(clipId: ClipId): FixtureSpec {
    const twin = UPLOAD_TWINS[clipId]
    return { ...twin, baseline: twin.baseline && scenario.baseline }
  }

  function requireCompleted(record: MockRecord, message: string): void {
    if (!isCompleted(record)) {
      throw new MockError('conflict', message)
    }
  }

  const isAuthenticated = (): boolean => !scenario.password || state.authenticated

  function config(): AppConfig {
    return {
      version: '2.0.0-mock',
      brain_backend: scenario.brainBackend,
      password_required: scenario.password,
      authenticated: isAuthenticated(),
      llm: { enabled: scenario.llm, model: scenario.llm ? MOCK_MODEL : null },
      languages: MOCK_LANGUAGES,
      limits: MOCK_LIMITS,
    }
  }

  function login(password: string): SessionInfo {
    const t = now()
    const recent = state.loginAttempts.filter((at) => at > t - MINUTE)
    if (recent.length >= LOGIN_LIMIT) {
      throw new MockError('rate_limited', 'Too many attempts. Wait a minute and try again.')
    }
    const ok = !scenario.password || password === MOCK_PASSWORD
    commit({ ...state, loginAttempts: [...recent, t], authenticated: ok || state.authenticated })
    if (!ok) {
      throw new MockError('unauthorized', 'Wrong password.')
    }
    return { authenticated: true }
  }

  function logout(): SessionInfo {
    commit({ ...state, authenticated: false })
    return { authenticated: false }
  }

  function warmup(): WarmupState {
    const t = now()
    if (t < state.gpu.warmingUntil) {
      return { warming: true }
    }
    if (t < state.gpu.warmUntil) {
      return { warming: false }
    }
    return { warming: claimGpu() }
  }

  function list(
    limit: number,
    before: string | null,
  ): { items: Analysis[]; nextBefore: string | null } {
    const sorted = [...state.records]
      .sort((a, b) => (a.id < b.id ? 1 : -1))
      .filter((record) => !before || record.id < before)
    const page = sorted.slice(0, limit)
    return {
      items: page.map((record) => render(record, false)),
      nextBefore: sorted.length > limit ? (page.at(-1)?.id ?? null) : null,
    }
  }

  function detail(id: string): AnalysisDetail {
    const record = find(id)
    return {
      analysis: render(record, true),
      result: hasMetrics(record, phase(record)) ? resultFor(record) : null,
      report: reportOf(record),
    }
  }

  function create(upload: ParsedUpload): Analysis {
    const clipId = clipFor(upload)
    const createdAt = now()
    const source = upload.file?.name ?? upload.script ?? ''
    const draft: MockRecord = {
      id: analysisId(createdAt, hashString(`${createdAt}:${state.records.length}:${source}`)),
      name: upload.name ?? defaultName(upload),
      clipId,
      createdAt,
      requestedLanguage: upload.language,
      language: languageFor(upload.language, clipId),
      fixture: freshFixture(clipId),
      llm: { status: scenario.llm ? 'ok' : 'skipped' },
      failure: scenario.failUploads ? UPLOAD_FAILURE : null,
      reusedFrom: null,
      sha256: fakeSha256(`${source}:${createdAt}`),
      job: null,
    }
    const record = startJob(draft, false)
    commit({ ...state, records: [...state.records, record] })
    return render(record, true)
  }

  function rename(id: string, name: string): Analysis {
    const trimmed = name.trim()
    if (trimmed.length < 1 || trimmed.length > 120) {
      throw new MockError('invalid_input', 'Names must be 1-120 characters.')
    }
    return render(
      updateRecord(id, (record) => ({ ...record, name: trimmed })),
      false,
    )
  }

  function remove(id: string): void {
    find(id)
    commit({
      ...state,
      records: state.records.filter((r) => r.id !== id),
      shares: state.shares.filter((s) => s.id !== id),
      comparisons: state.comparisons.filter((c) => c.a !== id && c.b !== id),
    })
  }

  function retry(id: string): Analysis {
    if (phase(find(id)).status !== 'failed') {
      throw new MockError('conflict', 'Only failed analyses can be retried.')
    }
    const next = updateRecord(id, (record) =>
      startJob(
        {
          ...record,
          fixture: freshFixture(record.clipId),
          failure: scenario.failUploads ? UPLOAD_FAILURE : null,
          llm: { status: scenario.llm ? 'ok' : 'skipped' },
        },
        false,
      ),
    )
    return render(next, true)
  }

  function regenerateReport(id: string): Analysis {
    const record = find(id)
    if (!scenario.llm) {
      throw new MockError(
        'unavailable',
        'No report model is configured. Set NM_LLM_MODEL to write reports.',
      )
    }
    requireCompleted(record, 'The report can be rewritten once the analysis is complete.')
    return render(
      updateRecord(id, (r) => startJob({ ...r, llm: { status: 'ok' } }, true)),
      true,
    )
  }

  function share(id: string): ShareLink {
    const record = find(id)
    requireCompleted(record, 'Only completed analyses can be shared.')
    const expiresAt = now() + SHARE_MS
    const token = `${base64url(record.id)}.${hashString(`${record.id}:${expiresAt}`).toString(36)}`
    commit({ ...state, shares: [...state.shares, { token, id: record.id, expiresAt }] })
    return { token, path: `/s/${token}`, expires_at: new Date(expiresAt).toISOString() }
  }

  function sharedId(token: string): string {
    const found = state.shares.find((s) => s.token === token)
    if (!found || found.expiresAt < now() || !state.records.some((r) => r.id === found.id)) {
      throw new MockError('not_found', 'This link has expired, or the analysis was deleted.')
    }
    return found.id
  }

  function comparison(aId: string, bId: string): ComparisonState {
    const a = find(aId)
    const b = find(bId)
    const job = state.comparisons.find((c) => c.a === aId && c.b === bId)
    return comparisonOf({
      job,
      elapsedMs: job ? (now() - job.startedAt) * scenario.speed : 0,
      nowIso: nowIso(),
      a: { id: aId, clipId: a.clipId, result: builtFor(a).result },
      b: { id: bId, clipId: b.clipId, result: builtFor(b).result },
    })
  }

  function compare(aId: string, bId: string): ComparisonState {
    if (aId === bId) {
      throw new MockError('invalid_input', 'Choose two different analyses.')
    }
    const message = 'Both analyses must be complete before they can be compared.'
    requireCompleted(find(aId), message)
    requireCompleted(find(bId), message)
    if (!scenario.llm) {
      throw new MockError(
        'unavailable',
        'Written comparisons need a report model. The metrics are compared below.',
      )
    }
    const current = comparison(aId, bId)
    if (current.status === 'completed' || current.status === 'running') {
      return current
    }
    const job = { a: aId, b: bId, startedAt: now(), fail: scenario.failComparison }
    const others = state.comparisons.filter((c) => c.a !== aId || c.b !== bId)
    commit({ ...state, comparisons: [...others, job] })
    return comparison(aId, bId)
  }

  /** Brain frames of an analysis whose metrics are ready. */
  function framesOf(id: string): Promise<Uint8Array> {
    const record = find(id)
    if (!hasMetrics(record, phase(record))) {
      return Promise.reject(new MockError('not_found', 'Brain frames are not ready yet.'))
    }
    const key = `${fixtureKey(record)}|${record.language}`
    const cached = synthesized.get(key)
    if (cached) {
      return cached
    }
    const { result } = builtFor(record)
    const count = result.frames?.n_frames ?? result.times.length
    const pending = loadBrainAssets().then((assets) =>
      synthesizeFrames(assets, result.systems, count, record.fixture.seed),
    )
    synthesized.set(key, pending)
    pending.catch(() => synthesized.delete(key))
    return pending
  }

  return {
    scenario,
    state: () => state,
    record: find,
    config,
    isAuthenticated,
    login,
    logout,
    warmup,
    list,
    status: (id: string) => render(find(id), true),
    detail,
    create,
    rename,
    remove,
    retry,
    regenerateReport,
    share,
    sharedId,
    compare,
    comparison,
    frames: framesOf,
  }
}
