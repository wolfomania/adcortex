// Synthetic system responses that follow what happens in a mock clip.
//
// Like the backend's mock brain, visual systems react to cuts and busy
// pictures, sound follows loudness, speech follows the voice-over, and the
// rest drift. Scene kinds add content cues (faces, places, product, brand),
// so the curves tell a story that matches the video. None of it is a brain
// prediction.
import { SYSTEM_CATALOG } from '@/features/systems/catalog'

import type { Clip, SceneKind } from './clips'
import { createRandom, drift, round, smooth, zscore } from './math'

type Trait = 'complexity' | 'motion' | 'faces' | 'places' | 'product' | 'brand'
type Feature = Trait | 'cuts' | 'loudness' | 'speech' | 'change'

const TRAITS: Record<SceneKind, Record<Trait, number>> = {
  title: { complexity: 0.2, motion: 0.15, faces: 0, places: 0, product: 0.1, brand: 1 },
  city: { complexity: 1, motion: 0.9, faces: 0, places: 1, product: 0, brand: 0 },
  presenter: { complexity: 0.4, motion: 0.2, faces: 1, places: 0.1, product: 0.2, brand: 0.2 },
  product: { complexity: 0.5, motion: 0.5, faces: 0, places: 0, product: 1, brand: 0.4 },
  lifestyle: { complexity: 0.85, motion: 0.6, faces: 0.1, places: 0.8, product: 0.3, brand: 0 },
  endcard: { complexity: 0.2, motion: 0, faces: 0, places: 0, product: 0.6, brand: 1 },
  audio: { complexity: 0, motion: 0, faces: 0, places: 0, product: 0, brand: 0 },
}

/** How strongly each feature drives each system, plus slow drift. */
const DRIVERS: Record<string, Partial<Record<Feature | 'drift', number>>> = {
  visual: { cuts: 1.1, complexity: 1, drift: 0.3 },
  motion: { motion: 1.2, cuts: 0.5, drift: 0.3 },
  faces: { faces: 1.6, drift: 0.3 },
  scenes: { places: 1.4, cuts: 0.3, drift: 0.3 },
  sound: { loudness: 1.3, drift: 0.2 },
  speech: { speech: 1.5, drift: 0.2 },
  social: { faces: 0.8, speech: 0.5, drift: 0.5 },
  attention: { cuts: 0.7, change: 0.5, drift: 0.4 },
  salience: { change: 0.8, cuts: 0.4, brand: 0.4, drift: 0.3 },
  valuation: { product: 1, brand: 0.6, drift: 0.5 },
}

/**
 * Fixed centring of each feature (not per clip), so a clip without faces
 * keeps a low faces response instead of having its noise stretched.
 */
const SCALE: Record<Feature, { center: number; gain: number }> = {
  cuts: { center: 0.1, gain: 1.5 },
  loudness: { center: 0.5, gain: 3 },
  change: { center: 0.05, gain: 6 },
  speech: { center: 0.4, gain: 2 },
  complexity: { center: 0.3, gain: 2 },
  motion: { center: 0.3, gain: 2 },
  faces: { center: 0.3, gain: 2 },
  places: { center: 0.3, gain: 2 },
  product: { center: 0.3, gain: 2 },
  brand: { center: 0.3, gain: 2 },
}

const NOISE_SD = 0.3
const HEMODYNAMIC = [0.25, 0.5, 0.25]
/** Reference-scaled curves are a little narrower than clip-relative ones. */
const BASELINE_GAIN = 0.8

/** 1 Hz samples covering the clip, as the backend's `seconds_grid`. */
export function secondsGrid(duration: number): number {
  return Math.max(1, Math.ceil(duration - 1e-6))
}

function overlap(start: number, end: number, from: number, to: number): number {
  return Math.max(0, Math.min(end, to) - Math.max(start, from))
}

function cutsOf(clip: Clip, n: number): number[] {
  const out = new Array<number>(n).fill(0)
  if (clip.kind !== 'video') {
    return out
  }
  for (const scene of clip.scenes) {
    const second = Math.floor(scene.start + 0.05)
    if (second < n) {
      out[second] = out[second]! + 1
    }
    if (second + 1 < n) {
      out[second + 1] = out[second + 1]! + 0.5
    }
  }
  return out
}

function loudnessOf(clip: Clip, n: number): number[] {
  return Array.from({ length: n }, (_, k) => {
    const window = clip.envelope.slice(k * 10, (k + 1) * 10)
    return window.length ? window.reduce((a, b) => a + b, 0) / window.length : 0
  })
}

/** Per-second feature curves of a clip. */
export function featureCurves(clip: Clip, n: number): Record<Feature, number[]> {
  const seconds = Array.from({ length: n }, (_, k) => k)
  const loudness = loudnessOf(clip, n)
  const trait = (name: Trait) =>
    seconds.map((k) =>
      clip.scenes.reduce(
        (sum, scene) => sum + overlap(scene.start, scene.end, k, k + 1) * TRAITS[scene.kind][name],
        0,
      ),
    )
  return {
    cuts: cutsOf(clip, n),
    loudness,
    change: loudness.map((value, k) => Math.abs(value - (loudness[k - 1] ?? value))),
    speech: seconds.map((k) =>
      clip.sentences.reduce((sum, s) => sum + overlap(s.start, s.end, k, k + 1), 0),
    ),
    complexity: trait('complexity'),
    motion: trait('motion'),
    faces: trait('faces'),
    places: trait('places'),
    product: trait('product'),
    brand: trait('brand'),
  }
}

/** Is the system meaningful for this kind of media? Visual systems need a picture. */
export function isApplicable(systemId: string, clip: Pick<Clip, 'kind'>): boolean {
  const system = SYSTEM_CATALOG.find((item) => item.id === systemId)
  return clip.kind === 'video' || !system?.visual
}

export interface CurveOptions {
  seed: number
  /** Scale curves against a reference set (true) or the clip itself (false). */
  baseline: boolean
  /** Shift of each system's level against the reference set, in SD. */
  offsets?: Partial<Record<string, number>>
}

function rawSignal(
  weights: Partial<Record<Feature | 'drift', number>>,
  normalized: Record<Feature, number[]>,
  slow: number[],
  noise: () => number,
): number[] {
  return slow.map((driftValue, k) => {
    let value = (weights.drift ?? 0) * driftValue + noise()
    for (const [feature, weight] of Object.entries(weights)) {
      if (feature !== 'drift') {
        value += (weight ?? 0) * normalized[feature as Feature][k]!
      }
    }
    return value
  })
}

/** z-score curves per system (1 Hz), keyed by system id. */
export function systemCurves(clip: Clip, options: CurveOptions): Record<string, number[]> {
  const n = secondsGrid(clip.duration)
  const random = createRandom(options.seed)
  const features = featureCurves(clip, n)
  const normalized = Object.fromEntries(
    Object.entries(features).map(([name, values]) => {
      const { center, gain } = SCALE[name as Feature]
      return [name, values.map((value) => (value - center) * gain)]
    }),
  ) as Record<Feature, number[]>
  const curves: Record<string, number[]> = {}
  for (const system of SYSTEM_CATALOG) {
    const noise = () => random.normal(0, NOISE_SD)
    const slow = drift(random, n)
    const applicable = isApplicable(system.id, clip)
    const weights = applicable ? (DRIVERS[system.id] ?? { drift: 1 }) : { drift: 0.2 }
    const signal = smooth(rawSignal(weights, normalized, slow, noise), HEMODYNAMIC)
    // Without a reference set the backend z-scores each curve against the
    // clip itself; with one, the level carries over.
    const offset = options.offsets?.[system.id] ?? 0
    curves[system.id] = options.baseline
      ? signal.map((value) => round(value * BASELINE_GAIN + offset, 3))
      : zscore(signal).map((value) => round(value, 3))
  }
  return curves
}
