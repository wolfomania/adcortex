// Synthetic per-second cortical maps for the 3D viewer.
//
// Each system's curve is painted over its atlas parcels, then spread a few
// millimetres over the surface (diffusion along mesh edges), so the maps
// look like smooth activation patterns rather than a coloured atlas. Slow
// spatial noise keeps the rest of the cortex alive.
import type { SystemSeries } from '@/api/types'
import { HEMISPHERE_VERTICES, N_VERTICES, type BrainAssets } from '@/features/brain/assets'
import { SYSTEM_CATALOG } from '@/features/systems/catalog'

import { createRandom, drift } from './math'

const SPREAD_ITERATIONS = 10
const NOISE_ITERATIONS = 40
const NOISE_FIELDS = 3
const NOISE_GAIN = 0.4
const NOT_APPLICABLE_GAIN = 0.3
const Z_RANGE = 3

export interface Graph {
  offsets: Uint32Array
  neighbors: Uint32Array
}

/** Neighbour lists of both hemispheres in CSR layout (global vertex ids). */
export function meshGraph(faces: { left: Uint16Array; right: Uint16Array }): Graph {
  const degree = new Uint32Array(N_VERTICES)
  const each = (visit: (a: number, b: number) => void) => {
    ;(['left', 'right'] as const).forEach((hemisphere, h) => {
      const list = faces[hemisphere]
      const base = h * HEMISPHERE_VERTICES
      for (let f = 0; f < list.length; f += 3) {
        const a = base + list[f]!
        const b = base + list[f + 1]!
        const c = base + list[f + 2]!
        visit(a, b)
        visit(b, c)
        visit(c, a)
      }
    })
  }
  each((a, b) => {
    degree[a]! += 1
    degree[b]! += 1
  })
  const offsets = new Uint32Array(N_VERTICES + 1)
  for (let v = 0; v < N_VERTICES; v += 1) {
    offsets[v + 1] = offsets[v]! + degree[v]!
  }
  const neighbors = new Uint32Array(offsets[N_VERTICES]!)
  const cursor = offsets.slice(0, N_VERTICES)
  each((a, b) => {
    neighbors[cursor[a]!++] = b
    neighbors[cursor[b]!++] = a
  })
  return { offsets, neighbors }
}

/** Repeatedly average each vertex with its neighbours. */
export function diffuse(values: Float32Array, graph: Graph, iterations: number): Float32Array {
  let current = values
  for (let i = 0; i < iterations; i += 1) {
    const next = new Float32Array(current.length)
    for (let v = 0; v < current.length; v += 1) {
      const from = graph.offsets[v]!
      const to = graph.offsets[v + 1]!
      let sum = 0
      for (let j = from; j < to; j += 1) {
        sum += current[graph.neighbors[j]!]!
      }
      next[v] = to > from ? 0.5 * current[v]! + (0.5 * sum) / (to - from) : current[v]!
    }
    current = next
  }
  return current
}

function normalizePeak(values: Float32Array): Float32Array {
  let peak = 0
  for (const value of values) {
    peak = Math.max(peak, Math.abs(value))
  }
  return peak > 0 ? values.map((value) => value / peak) : values
}

/** Smoothly spread loading (0-1) of each system over the cortex. */
function systemLoadings(
  assets: BrainAssets,
  graph: Graph,
  seed: number,
): Map<string, Float32Array> {
  const random = createRandom(seed)
  const parcelGain = assets.atlas.parcels.map(() => 0.7 + 0.6 * random.next())
  const idByName = new Map(assets.atlas.parcels.filter(Boolean).map((p) => [p.name, p.id]))
  const loadings = new Map<string, Float32Array>()
  for (const system of SYSTEM_CATALOG) {
    const members = new Set(system.parcels.map((name) => idByName.get(name)))
    const indicator = new Float32Array(N_VERTICES)
    assets.mesh.parcel.forEach((parcel, v) => {
      indicator[v] = members.has(parcel) ? (parcelGain[parcel] ?? 1) : 0
    })
    loadings.set(system.id, normalizePeak(diffuse(indicator, graph, SPREAD_ITERATIONS)))
  }
  return loadings
}

function noiseFields(graph: Graph, seed: number): Float32Array[] {
  const random = createRandom(seed ^ 0x5bd1e995)
  return Array.from({ length: NOISE_FIELDS }, () => {
    const field = new Float32Array(N_VERTICES).map(() => random.normal())
    return normalizePeak(diffuse(field, graph, NOISE_ITERATIONS))
  })
}

function quantize(z: number): number {
  const clipped = Math.max(-Z_RANGE, Math.min(Z_RANGE, z))
  return Math.round(((clipped + Z_RANGE) / (2 * Z_RANGE)) * 255)
}

/**
 * Frames as the API serves them: `n_frames × 20484` bytes, where byte `b`
 * stands for z = -3 + b / 255 × 6.
 */
export function synthesizeFrames(
  assets: BrainAssets,
  systems: readonly SystemSeries[],
  nFrames: number,
  seed: number,
): Uint8Array {
  const graph = meshGraph(assets.mesh.faces)
  const loadings = systemLoadings(assets, graph, seed)
  const fields = noiseFields(graph, seed)
  const random = createRandom(seed ^ 0x9e3779b9)
  const coefficients = fields.map(() => drift(random, nFrames))
  const out = new Uint8Array(nFrames * N_VERTICES)
  const z = new Float32Array(N_VERTICES)
  for (let k = 0; k < nFrames; k += 1) {
    z.fill(0)
    for (const series of systems) {
      const loading = loadings.get(series.id)
      const value =
        (series.values[k] ?? 0) * (series.applicable === false ? NOT_APPLICABLE_GAIN : 1)
      if (loading && value !== 0) {
        for (let v = 0; v < N_VERTICES; v += 1) {
          z[v]! += loading[v]! * value
        }
      }
    }
    fields.forEach((field, j) => {
      const weight = NOISE_GAIN * (coefficients[j]![k] ?? 0)
      for (let v = 0; v < N_VERTICES; v += 1) {
        z[v]! += weight * field[v]!
      }
    })
    const row = k * N_VERTICES
    for (let v = 0; v < N_VERTICES; v += 1) {
      out[row + v] = assets.mesh.parcel[v] === 0 ? 128 : quantize(z[v]!)
    }
  }
  return out
}
