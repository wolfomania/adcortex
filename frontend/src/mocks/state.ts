// The mock backend's state: plain JSON, so it can survive page reloads.
import { CLIPS } from './fixtures/clips'
import { hashString } from './fixtures/math'
import { ENGLISH, SEEDS, type SeedSpec } from './fixtures/seeds'
import { analysisId, type MockRecord } from './records'

export const STATE_VERSION = 3

export interface Share {
  token: string
  id: string
  expiresAt: number
}

export interface ComparisonJob {
  a: string
  b: string
  startedAt: number
  fail: boolean
}

export interface MockState {
  version: number
  /** The scenario flags the state was made for. */
  scenario: string
  records: MockRecord[]
  shares: Share[]
  comparisons: ComparisonJob[]
  authenticated: boolean
  /** Wall-clock times (ms) the GPU worker is warming until, and warm until. */
  gpu: { warmingUntil: number; warmUntil: number }
  loginAttempts: number[]
}

const MINUTE = 60_000

/** A fake SHA-256 hex digest, stable for a given text. */
export function fakeSha256(text: string): string {
  return Array.from({ length: 8 }, (_, i) =>
    hashString(`${text}#${i}`).toString(16).padStart(8, '0'),
  ).join('')
}

function seedRecord(spec: SeedSpec, anchor: number): MockRecord {
  const clip = CLIPS[spec.clipId]
  const createdAt = anchor - spec.ageMinutes * MINUTE
  const language = spec.language ?? ENGLISH
  return {
    id: analysisId(createdAt, hashString(spec.key)),
    name: spec.name,
    clipId: spec.clipId,
    createdAt,
    requestedLanguage: language.requested ?? 'auto',
    language,
    fixture: spec.fixture,
    llm: { status: spec.llm, error: spec.llmError },
    failure: spec.failure ?? null,
    reusedFrom: null,
    // Re-runs of the same file share the digest, as the backend's reuse requires.
    sha256: fakeSha256(`${clip.id}:${spec.reusedFromKey ?? spec.key}`),
    job: null,
  }
}

/** The starting state: the seeded history, ending `anchor` (ms). */
export function seedState(scenario: string, anchor: number, empty: boolean): MockState {
  const byKey = new Map(SEEDS.map((spec) => [spec.key, seedRecord(spec, anchor)]))
  const records = empty
    ? []
    : SEEDS.map((spec) => {
        const record = byKey.get(spec.key)!
        const source = spec.reusedFromKey ? byKey.get(spec.reusedFromKey) : undefined
        return source ? { ...record, reusedFrom: source.id } : record
      })
  return {
    version: STATE_VERSION,
    scenario,
    records,
    shares: [],
    comparisons: [],
    authenticated: false,
    gpu: { warmingUntil: 0, warmUntil: 0 },
    loginAttempts: [],
  }
}

/** Accept a restored state only if it has the current shape. */
export function isMockState(value: unknown, scenario: string): value is MockState {
  if (typeof value !== 'object' || value === null) {
    return false
  }
  const state = value as Partial<MockState>
  return (
    state.version === STATE_VERSION &&
    state.scenario === scenario &&
    Array.isArray(state.records) &&
    state.records.every((record) => record.clipId in CLIPS) &&
    Array.isArray(state.shares) &&
    Array.isArray(state.comparisons) &&
    Array.isArray(state.loginAttempts) &&
    typeof state.gpu === 'object'
  )
}
