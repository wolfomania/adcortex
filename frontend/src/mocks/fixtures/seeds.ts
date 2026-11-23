// The history the mock backend starts with.
import type { LanguageInfo } from '@/api/types'
import { SYSTEM_CATALOG } from '@/features/systems/catalog'

import type { ClipId, Sentence } from './clips'
import { createRandom } from './math'

export type LlmOutcome = 'ok' | 'skipped' | 'failed'

/** Everything that decides the synthetic metrics of an analysis. */
export interface FixtureSpec {
  seed: number
  baseline: boolean
  offsets?: Record<string, number>
  /** Replaces the clip's transcript. */
  sentences?: Sentence[]
}

export interface SeedSpec {
  key: string
  name: string
  clipId: ClipId
  /** Minutes before the history's anchor time. */
  ageMinutes: number
  fixture: FixtureSpec
  language?: LanguageInfo
  llm: LlmOutcome
  llmError?: string
  /** Set for an analysis that failed; the message is shown as is. */
  failure?: string
  reusedFromKey?: string
}

export const ENGLISH: LanguageInfo = { requested: 'auto', detected: 'en', full_support: true }

const LUMEN_30: FixtureSpec = {
  seed: 30,
  baseline: true,
  offsets: {
    faces: 0.2,
    valuation: 0.05,
    speech: 0.05,
    social: 0.1,
    visual: -0.4,
    scenes: -0.15,
    sound: -0.15,
    attention: -0.3,
    salience: -0.5,
    motion: -0.2,
  },
}

const LUMEN_15: FixtureSpec = {
  seed: 15,
  baseline: true,
  offsets: {
    valuation: -0.25,
    salience: -0.55,
    attention: -0.35,
    visual: -0.45,
    motion: -0.15,
    speech: -0.1,
    faces: 0.4,
    social: 0.2,
    scenes: 0.1,
  },
}

const RADIO_20: FixtureSpec = { seed: 20, baseline: false }

const SCRIPT_15: FixtureSpec = {
  seed: 115,
  baseline: true,
  offsets: { speech: -0.75, salience: -0.45, attention: -0.3, valuation: 0.55, social: 0.15 },
}

/**
 * The fixture a new upload of each clip gets: the one the hand-written report
 * describes, so a fresh analysis reads as coherently as the seeded one.
 */
export const UPLOAD_TWINS: Record<ClipId, FixtureSpec> = {
  'lumen-30s': LUMEN_30,
  'lumen-15s': LUMEN_15,
  'radio-20s': RADIO_20,
  'script-15s': SCRIPT_15,
}

/** An older draft: level shifts so the library has some spread. */
function draft(seed: number): FixtureSpec {
  const random = createRandom(seed)
  const offsets = Object.fromEntries(SYSTEM_CATALOG.map((s) => [s.id, random.normal(-0.15, 0.3)]))
  return { seed, baseline: true, offsets }
}

const SPANISH_DUB: Sentence[] = [
  { start: 0.4, end: 1.48, text: 'Conoce Lumen.' },
  { start: 2.9, end: 5.73, text: 'Cálida cuando descansas. Brillante cuando te concentras.' },
  { start: 11.4, end: 13.42, text: 'Lumen. Ya disponible.' },
]

const DAY = 24 * 60

export const LLM_TIMEOUT_ERROR =
  'The report model did not answer within 240 seconds. The metrics are complete; write the report again to retry.'

export const SEEDS: readonly SeedSpec[] = [
  {
    key: 'lumen-30',
    name: 'Lumen launch: 30s master',
    clipId: 'lumen-30s',
    ageMinutes: 95,
    fixture: LUMEN_30,
    llm: 'ok',
  },
  {
    key: 'lumen-15',
    name: 'Lumen launch: 15s cut-down',
    clipId: 'lumen-15s',
    ageMinutes: 70,
    fixture: LUMEN_15,
    llm: 'ok',
  },
  {
    key: 'rerun',
    name: 'Lumen launch: 30s master (re-run)',
    clipId: 'lumen-30s',
    ageMinutes: 40,
    fixture: LUMEN_30,
    llm: 'ok',
    reusedFromKey: 'lumen-30',
  },
  {
    key: 'radio',
    name: 'Lumen radio spot',
    clipId: 'radio-20s',
    ageMinutes: 26 * 60,
    fixture: RADIO_20,
    llm: 'failed',
    llmError: LLM_TIMEOUT_ERROR,
  },
  {
    key: 'script',
    name: 'Lumen script: draft 2',
    clipId: 'script-15s',
    ageMinutes: 2 * DAY,
    fixture: SCRIPT_15,
    language: { requested: 'en', detected: 'en', full_support: true },
    llm: 'ok',
  },
  {
    key: 'dub-es',
    name: 'Lumen 15s: Spanish dub',
    clipId: 'lumen-15s',
    ageMinutes: 3 * DAY,
    fixture: { ...draft(1515), sentences: SPANISH_DUB },
    language: { requested: 'auto', detected: 'es', full_support: false },
    llm: 'skipped',
  },
  {
    key: 'broken',
    name: 'Holiday teaser',
    clipId: 'lumen-30s',
    ageMinutes: 4 * DAY,
    fixture: draft(404),
    llm: 'skipped',
    failure:
      "We couldn't read the video stream in this file. Export it again as H.264 MP4 and upload it once more.",
  },
  {
    key: 'v3',
    name: 'Lumen 30s: rough cut v3',
    clipId: 'lumen-30s',
    ageMinutes: 6 * DAY,
    fixture: draft(303),
    llm: 'skipped',
  },
  {
    key: 'alt-end',
    name: 'Lumen 15s: alternate end card',
    clipId: 'lumen-15s',
    ageMinutes: 7 * DAY,
    fixture: draft(1503),
    llm: 'skipped',
  },
  {
    key: 'radio-f',
    name: 'Lumen radio: female voice',
    clipId: 'radio-20s',
    ageMinutes: 8 * DAY,
    fixture: draft(2002),
    llm: 'skipped',
  },
  {
    key: 'v2',
    name: 'Lumen 30s: rough cut v2',
    clipId: 'lumen-30s',
    ageMinutes: 10 * DAY,
    fixture: draft(302),
    llm: 'skipped',
  },
  {
    key: 'alt-music',
    name: 'Lumen 15s: alternate music',
    clipId: 'lumen-15s',
    ageMinutes: 12 * DAY,
    fixture: draft(1502),
    llm: 'skipped',
  },
  {
    key: 'script-1',
    name: 'Lumen script: draft 1',
    clipId: 'script-15s',
    ageMinutes: 14 * DAY,
    fixture: draft(1151),
    llm: 'skipped',
  },
  {
    key: 'v1',
    name: 'Lumen 30s: rough cut v1',
    clipId: 'lumen-30s',
    ageMinutes: 16 * DAY,
    fixture: draft(301),
    llm: 'skipped',
  },
]
