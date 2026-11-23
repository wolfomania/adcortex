// Starts the mock backend in the browser (development only).
//
// Open the app with `?mock=<flags>` to pick a scenario, for example
// `?mock=password,nollm`; `?mock=` returns to the default, and adding `reset`
// starts over from the seeded history. See scenario.ts for the flags.
import { setupWorker } from 'msw/browser'

import { createMockDb } from './db'
import { createHandlers } from './handlers'
import { parseScenario } from './scenario'
import { isMockState, seedState, type MockState } from './state'

const SCENARIO_KEY = 'adcortex-mock-scenario'
const STATE_KEY = 'adcortex-mock-state'

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStorage(key: string, value: string | null): void {
  try {
    if (value === null) {
      window.localStorage.removeItem(key)
    } else {
      window.localStorage.setItem(key, value)
    }
  } catch {
    // Storage can be full or blocked; the mock then forgets changes on reload.
  }
}

/** The scenario flags from `?mock=`, remembered for later page loads. */
function scenarioFlags(): { flags: string; reset: boolean } {
  const fromUrl = new URLSearchParams(window.location.search).get('mock')
  const raw = fromUrl ?? readStorage(SCENARIO_KEY) ?? ''
  const all = raw
    .split(',')
    .map((flag) => flag.trim().toLowerCase())
    .filter(Boolean)
  const flags = all
    .filter((flag) => flag !== 'reset')
    .sort()
    .join(',')
  writeStorage(SCENARIO_KEY, flags)
  return { flags, reset: all.includes('reset') }
}

function restore(flags: string): MockState | null {
  const text = readStorage(STATE_KEY)
  if (!text) {
    return null
  }
  try {
    const value: unknown = JSON.parse(text)
    return isMockState(value, flags) ? value : null
  } catch {
    return null
  }
}

export async function startMockBackend(): Promise<void> {
  const { flags, reset } = scenarioFlags()
  const scenario = parseScenario(flags)
  const state = (!reset && restore(flags)) || seedState(flags, Date.now(), scenario.empty)
  writeStorage(STATE_KEY, JSON.stringify(state))
  const db = createMockDb({
    scenario,
    state,
    onChange: (next) => writeStorage(STATE_KEY, JSON.stringify(next)),
  })
  const worker = setupWorker(...createHandlers(() => db))
  await worker.start({
    serviceWorker: { url: '/mockServiceWorker.js' },
    onUnhandledFrame: 'bypass',
    quiet: true,
  })
}
