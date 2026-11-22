import { describe, expect, it } from 'vitest'

import { DEFAULT_SCENARIO, parseScenario } from './scenario'

describe('parseScenario', () => {
  it('applies known flags and ignores the rest', () => {
    const scenario = parseScenario('password, nollm,instant,unknown')

    expect(scenario.password).toBe(true)
    expect(scenario.llm).toBe(false)
    expect(scenario.speed).toBe(1000)
  })

  it('returns the default without flags', () => {
    expect(parseScenario(null)).toEqual(DEFAULT_SCENARIO)
    expect(parseScenario('')).toEqual(DEFAULT_SCENARIO)
  })
})
