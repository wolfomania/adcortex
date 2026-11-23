// Pure helpers of the comparison page.
import type { AnalysisResult, SystemSeries } from '@/api/types'

export interface ScoreRow {
  label: string
  a: number | null
  b: number | null
  unit: string
}

export function scoreRows(a: AnalysisResult, b: AnalysisResult): ScoreRow[] {
  return [
    { label: 'Response index', a: a.scores.response_index, b: b.scores.response_index, unit: '' },
    { label: 'Hook', a: a.scores.hook, b: b.scores.hook, unit: '' },
    { label: 'Sustain', a: a.scores.sustain, b: b.scores.sustain, unit: '%' },
    { label: 'Peaks', a: a.scores.peak_count, b: b.scores.peak_count, unit: '' },
  ]
}

/** B minus A with its sign (true minus), or a dash when either is missing. */
export function formatDelta(a: number | null, b: number | null): string {
  if (a === null || b === null) {
    return '–'
  }
  const delta = Math.round(b) - Math.round(a)
  return delta > 0 ? `+${delta}` : delta < 0 ? `−${Math.abs(delta)}` : '±0'
}

export interface SystemPair {
  id: string
  label: string
  a: SystemSeries | undefined
  b: SystemSeries | undefined
}

/** The systems of both analyses, in A's order, then any only B has. */
export function pairSystems(a: AnalysisResult, b: AnalysisResult): SystemPair[] {
  const byId = new Map(b.systems.map((system) => [system.id, system]))
  const pairs: SystemPair[] = a.systems.map((system) => ({
    id: system.id,
    label: system.label,
    a: system,
    b: byId.get(system.id),
  }))
  const seen = new Set(pairs.map((pair) => pair.id))
  for (const system of b.systems) {
    if (!seen.has(system.id)) {
      pairs.push({ id: system.id, label: system.label, a: undefined, b: system })
    }
  }
  return pairs
}

/** A symmetric z range that fits every value, in steps of 0.5, at least ±1. */
export function zExtent(curves: readonly (readonly (number | null)[])[]): number {
  let peak = 0
  for (const curve of curves) {
    for (const value of curve) {
      if (value !== null) {
        peak = Math.max(peak, Math.abs(value))
      }
    }
  }
  return Math.max(1, Math.ceil(peak * 2) / 2)
}
