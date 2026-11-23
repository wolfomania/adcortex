import { describe, expect, it } from 'vitest'

import type { AnalysisResult, SystemSeries } from '@/api/types'

import { formatDelta, pairSystems, scoreRows, zExtent } from './compare'

function system(id: string): SystemSeries {
  return { id, label: id.toUpperCase(), confidence: 'high', values: [], mean_z: 0 }
}

function result(ids: string[], response: number | null = 50): AnalysisResult {
  return {
    duration_s: 3,
    times: [0, 1, 2],
    systems: ids.map(system),
    scenes: [],
    scene_stats: [],
    moments: [],
    scores: { response_index: response, hook: 40, sustain: null, peak_count: 2 },
    transcript: [],
    language: {},
  } as unknown as AnalysisResult
}

describe('comparison helpers', () => {
  it('signs the difference of B against A', () => {
    expect(formatDelta(50, 62.4)).toBe('+12')
    expect(formatDelta(62, 50)).toBe('−12')
    expect(formatDelta(50, 50.2)).toBe('±0')
    expect(formatDelta(null, 50)).toBe('–')
  })

  it('lists the four scores of both analyses', () => {
    const rows = scoreRows(result(['v'], 70), result(['v'], null))

    expect(rows.map((row) => row.label)).toEqual(['Response index', 'Hook', 'Sustain', 'Peaks'])
    expect(rows[0]).toMatchObject({ a: 70, b: null })
  })

  it('pairs systems by id and keeps the ones only B has', () => {
    const pairs = pairSystems(result(['faces', 'speech']), result(['speech', 'sound']))

    expect(pairs.map((pair) => [pair.id, Boolean(pair.a), Boolean(pair.b)])).toEqual([
      ['faces', true, false],
      ['speech', true, true],
      ['sound', false, true],
    ])
  })

  it('rounds the chart range up to half steps', () => {
    expect(zExtent([[0.2, null]])).toBe(1)
    expect(zExtent([[0.2], [-1.3]])).toBe(1.5)
  })
})
