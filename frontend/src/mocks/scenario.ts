// Switches for the mock backend, so every state of the app can be reached
// in development: open the app with `?mock=password,nollm,...`.
import type { AppConfig } from '@/api/types'

export interface Scenario {
  /** ADCORTEX_PASSWORD is set: log in with MOCK_PASSWORD. */
  password: boolean
  /** A report model is configured. */
  llm: boolean
  /** A reference set (baseline) is loaded. */
  baseline: boolean
  /** New analyses fail while predicting. */
  failUploads: boolean
  /** Comparisons fail. */
  failComparison: boolean
  brainBackend: AppConfig['brain_backend']
  /** Start without history. */
  empty: boolean
  /** How much faster than real time new analyses progress. */
  speed: number
  /** Added to every response, in milliseconds. */
  latencyMs: number
}

export const MOCK_PASSWORD = 'lumen'

export const DEFAULT_SCENARIO: Scenario = {
  password: false,
  llm: true,
  baseline: true,
  failUploads: false,
  failComparison: false,
  brainBackend: 'tribe',
  empty: false,
  speed: 1,
  latencyMs: 120,
}

const FLAGS: Record<string, (scenario: Scenario) => Scenario> = {
  password: (s) => ({ ...s, password: true }),
  nollm: (s) => ({ ...s, llm: false }),
  nobaseline: (s) => ({ ...s, baseline: false }),
  fail: (s) => ({ ...s, failUploads: true }),
  comparefail: (s) => ({ ...s, failComparison: true }),
  demo: (s) => ({ ...s, brainBackend: 'mock' }),
  replay: (s) => ({ ...s, brainBackend: 'replay' }),
  empty: (s) => ({ ...s, empty: true }),
  fast: (s) => ({ ...s, speed: 4 }),
  instant: (s) => ({ ...s, speed: 1000, latencyMs: 0 }),
  slow: (s) => ({ ...s, latencyMs: 900 }),
}

export const SCENARIO_FLAGS = Object.keys(FLAGS)

/** Parse a comma-separated flag list such as "password,nollm". */
export function parseScenario(text: string | null | undefined): Scenario {
  return (text ?? '')
    .split(',')
    .map((flag) => flag.trim().toLowerCase())
    .filter((flag) => flag in FLAGS)
    .reduce((scenario, flag) => FLAGS[flag]!(scenario), DEFAULT_SCENARIO)
}
