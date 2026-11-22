// Ports of the backend's deterministic metrics (analysis/moments.py,
// scores.py, run.py), so mock results are internally consistent.
import type { Moment, Scene, SceneStat, Scores, SystemSeries } from '@/api/types'

import { mean, normalCdf, round } from './math'

export const PEAK_Z = 1
export const PEAK_PROMINENCE = 0.75
export const MIN_DISTANCE_S = 3
export const MAX_MOMENTS = 12
export const HOOK_SECONDS = 3
export const TOP_SYSTEMS = 3

type Curve = readonly (number | null)[]

/** Lowest value between sample k and the next higher sample (or the edge). */
function base(valid: [number, number][], k: number, step: number): number {
  const peak = valid[k]![1]
  let lowest = peak
  for (let j = k + step; j >= 0 && j < valid.length; j += step) {
    const value = valid[j]![1]
    if (value > peak) {
      break
    }
    lowest = Math.min(lowest, value)
  }
  return lowest
}

/** Indices of local maxima, filtered by height, prominence, and spacing. */
export function findPeaks(
  values: Curve,
  options: { minHeight: number; minProminence: number; minDistance: number },
): number[] {
  const valid: [number, number][] = []
  values.forEach((value, i) => {
    if (value !== null) {
      valid.push([i, value])
    }
  })
  const candidates: [number, number][] = []
  valid.forEach(([i, v], k) => {
    const left = k > 0 ? valid[k - 1]![1] : Number.NEGATIVE_INFINITY
    const right = k + 1 < valid.length ? valid[k + 1]![1] : Number.NEGATIVE_INFINITY
    if (v > left && v >= right && v >= options.minHeight) {
      const prominence = v - Math.max(base(valid, k, -1), base(valid, k, 1))
      if (prominence >= options.minProminence) {
        candidates.push([i, v])
      }
    }
  })
  const chosen: number[] = []
  for (const [i] of [...candidates].sort((a, b) => b[1] - a[1])) {
    if (chosen.every((j) => Math.abs(i - j) >= options.minDistance)) {
      chosen.push(i)
    }
  }
  return chosen.sort((a, b) => a - b)
}

function peaksOf(values: Curve): number[] {
  return findPeaks(values, {
    minHeight: PEAK_Z,
    minProminence: PEAK_PROMINENCE,
    minDistance: MIN_DISTANCE_S,
  })
}

/** Strongest peaks and dips across systems, sorted by time. */
export function findMoments(
  curves: Record<string, Curve>,
  labels: Record<string, string>,
  limit = MAX_MOMENTS,
): Moment[] {
  const found: Moment[] = []
  for (const [systemId, values] of Object.entries(curves)) {
    const label = labels[systemId] ?? systemId
    for (const i of peaksOf(values)) {
      const z = values[i] ?? 0
      found.push({
        t: i,
        kind: 'peak',
        system_id: systemId,
        z: round(z, 2),
        label: `${label} peak (+${z.toFixed(1)} SD)`,
      })
    }
    for (const i of peaksOf(values.map((v) => (v === null ? null : -v)))) {
      const z = values[i] ?? 0
      found.push({
        t: i,
        kind: 'dip',
        system_id: systemId,
        z: round(z, 2),
        label: `${label} dip (${z.toFixed(1)} SD)`,
      })
    }
  }
  const strongest = [...found].sort((a, b) => Math.abs(b.z) - Math.abs(a.z)).slice(0, limit)
  return strongest.sort((a, b) => a.t - b.t || a.system_id.localeCompare(b.system_id))
}

/** Mean z per scene, from seconds whose centre lies inside the scene. */
export function sceneStats(
  scenes: readonly Scene[],
  curves: Record<string, Curve>,
  applicable: readonly string[],
): SceneStat[] {
  return scenes.map((scene) => {
    const means: Record<string, number> = {}
    for (const id of applicable) {
      const inside = (curves[id] ?? []).filter(
        (value, k): value is number =>
          value !== null && k + 0.5 >= scene.start && k + 0.5 < scene.end,
      )
      if (inside.length) {
        means[id] = round(mean(inside), 3)
      }
    }
    return { scene_index: scene.index, mean_z: means }
  })
}

/** Per-second mean across systems, ignoring gaps. */
export function composite(curves: Record<string, Curve>, ids: readonly string[]): number[] {
  const n = Math.max(0, ...ids.map((id) => curves[id]?.length ?? 0))
  return Array.from({ length: n }, (_, k) => {
    const present = ids
      .map((id) => curves[id]?.[k])
      .filter((v): v is number => typeof v === 'number')
    return present.length ? mean(present) : 0
  })
}

/** Reference percentile of a clip-mean z (reference clip means spread ~0.35 SD). */
export function referencePercentile(meanZ: number, spread = 0.35): number {
  return round(Math.min(99.5, Math.max(0.5, 100 * normalCdf(meanZ / spread))), 1)
}

export function computeScores(
  curves: Record<string, Curve>,
  applicable: readonly string[],
  percentiles: Record<string, number | null>,
  peakCount: number,
  hasBaseline: boolean,
): Scores {
  const ranked = applicable
    .map((id) => percentiles[id])
    .filter((p): p is number => typeof p === 'number')
  if (!hasBaseline) {
    return { response_index: null, hook: null, sustain: null, peak_count: peakCount }
  }
  const comp = composite(curves, applicable)
  const head = comp.slice(0, HOOK_SECONDS)
  return {
    response_index: ranked.length ? round(mean(ranked), 1) : null,
    hook: head.length ? referencePercentile(mean(head), 0.45) : null,
    sustain: comp.length ? round((100 * comp.filter((v) => v > 0).length) / comp.length, 1) : null,
    peak_count: peakCount,
  }
}

/** Applicable systems ranked by percentile, then mean z. */
export function topSystems(series: readonly SystemSeries[]): string[] {
  return series
    .filter((s) => s.applicable !== false)
    .sort((a, b) => (b.percentile ?? -1) - (a.percentile ?? -1) || b.mean_z - a.mean_z)
    .slice(0, TOP_SYSTEMS)
    .map((s) => s.id)
}
