// The mock backend for tests: the same handlers as development, on a fixed
// clock, plus the brain assets read from public/.
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

import { createMockDb, type MockDb } from '@/mocks/db'
import { createHandlers } from '@/mocks/handlers'
import { DEFAULT_SCENARIO, type Scenario } from '@/mocks/scenario'
import { seedState } from '@/mocks/state'

/** The tests' "now": 2026-11-22 12:00 UTC. */
export const TEST_NOW = Date.UTC(2026, 10, 22, 12, 0, 0)

// Vitest runs from the frontend directory (see vitest.config.ts).
const PUBLIC_DIR = resolve(process.cwd(), 'public')

export const clock = {
  now: TEST_NOW,
  /** Move the backend's clock forward. */
  advance(ms: number): void {
    clock.now += ms
  },
}

let db: MockDb = makeDb()

function makeDb(overrides: Partial<Scenario> = {}): MockDb {
  const scenario: Scenario = { ...DEFAULT_SCENARIO, latencyMs: 0, ...overrides }
  return createMockDb({
    scenario,
    state: seedState('test', TEST_NOW, scenario.empty),
    now: () => clock.now,
  })
}

/** Start every test from the seeded history and the default scenario. */
export function resetMockBackend(overrides: Partial<Scenario> = {}): MockDb {
  clock.now = TEST_NOW
  db = makeDb(overrides)
  return db
}

export function mockDb(): MockDb {
  return db
}

const brainAssets = http.get('*/brain/:file', async ({ params }) => {
  const file = String(params.file)
  if (!/^[\w.-]+$/.test(file)) {
    return new HttpResponse(null, { status: 404 })
  }
  try {
    const bytes = await readFile(resolve(PUBLIC_DIR, 'brain', file))
    const type = file.endsWith('.json') ? 'application/json' : 'application/octet-stream'
    const body = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
    return HttpResponse.arrayBuffer(body as ArrayBuffer, { headers: { 'Content-Type': type } })
  } catch {
    return new HttpResponse(null, { status: 404 })
  }
})

export const server = setupServer(brainAssets, ...createHandlers(() => db))
