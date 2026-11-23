// Deterministic randomness and small statistics helpers for the fixtures.

export interface Random {
  /** Uniform in [0, 1). */
  next(): number
  /** Normally distributed (Box-Muller). */
  normal(mean?: number, sd?: number): number
}

/** Seeded PRNG (mulberry32), so every fixture is identical on every run. */
export function createRandom(seed: number): Random {
  let state = seed >>> 0
  const next = () => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
  return {
    next,
    normal(mean = 0, sd = 1) {
      const u = Math.max(next(), 1e-12)
      const v = next()
      return mean + sd * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v)
    },
  }
}

/** FNV-1a hash of a string, for seeds and ids. */
export function hashString(text: string): number {
  let hash = 0x811c9dc5
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193)
  }
  return hash >>> 0
}

export function mean(values: readonly number[]): number {
  if (values.length === 0) {
    return 0
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

export function std(values: readonly number[]): number {
  const m = mean(values)
  return Math.sqrt(mean(values.map((value) => (value - m) ** 2)))
}

export function zscore(values: readonly number[]): number[] {
  const s = std(values)
  if (s < 1e-9) {
    return values.map(() => 0)
  }
  const m = mean(values)
  return values.map((value) => (value - m) / s)
}

/** Centered moving average with edge padding (odd window). */
export function smooth(values: readonly number[], kernel: readonly number[]): number[] {
  const half = Math.floor(kernel.length / 2)
  return values.map((_, i) =>
    kernel.reduce((sum, weight, k) => {
      const j = Math.min(values.length - 1, Math.max(0, i + k - half))
      return sum + weight * values[j]!
    }, 0),
  )
}

/** Standard normal cumulative distribution (Abramowitz-Stegun 7.1.26). */
export function normalCdf(x: number): number {
  const sign = x < 0 ? -1 : 1
  const z = Math.abs(x) / Math.SQRT2
  const t = 1 / (1 + 0.3275911 * z)
  const poly =
    ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t
  const erf = 1 - poly * Math.exp(-z * z)
  return 0.5 * (1 + sign * erf)
}

export function round(value: number, digits: number): number {
  const factor = 10 ** digits
  return Math.round(value * factor) / factor
}

/** A cumulative random walk, smoothed and z-scored: slow drift. */
export function drift(random: Random, n: number): number[] {
  let level = 0
  const walk = Array.from({ length: n }, () => {
    level += random.normal()
    return level
  })
  return zscore(smooth(walk, [1 / 3, 1 / 3, 1 / 3]))
}
