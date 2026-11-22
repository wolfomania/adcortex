// Pure helpers of the system timeline.

/** |z| at which a timeline cell reaches full color. */
export const HEAT_FULL_Z = 2

/** Cell fill for a z-score, on the diverging scale the brain view uses. */
export function heatFill(z: number | null | undefined): string {
  if (z === null || z === undefined) {
    return 'var(--surface-sunken)'
  }
  const strength = Math.round(Math.min(Math.abs(z) / HEAT_FULL_Z, 1) * 100)
  const hue = z >= 0 ? 'var(--viz-pos)' : 'var(--viz-neg)'
  return `color-mix(in oklch, ${hue} ${strength}%, var(--viz-mid))`
}

/** The time under a pointer at `clientX`, over a track spanning `left`…`left + width`. */
export function timeAtX(clientX: number, left: number, width: number, duration: number): number {
  if (width <= 0) {
    return 0
  }
  return Math.min(Math.max((clientX - left) / width, 0), 1) * duration
}

const TICK_STEPS = [1, 2, 5, 10, 15, 30, 60]

/** Axis ticks in seconds: the smallest step that gives at most 10 intervals. */
export function timeTicks(duration: number): number[] {
  const step = TICK_STEPS.find((s) => duration / s <= 10) ?? 120
  const ticks: number[] = []
  for (let t = 0; t <= duration + 1e-9; t += step) {
    ticks.push(t)
  }
  return ticks
}

/** Mean of the non-missing values; null when there are none. */
export function mean(values: readonly (number | null | undefined)[]): number | null {
  let sum = 0
  let count = 0
  for (const value of values) {
    if (value !== null && value !== undefined) {
      sum += value
      count += 1
    }
  }
  return count ? sum / count : null
}

interface CurveSystem {
  applicable?: boolean
  values: readonly (number | null | undefined)[]
}

/** The mean z-score of the applicable systems, second by second. */
export function meanCurve(systems: readonly CurveSystem[], length: number): (number | null)[] {
  const applicable = systems.filter((system) => system.applicable !== false)
  return Array.from({ length }, (_, k) => mean(applicable.map((system) => system.values[k])))
}
