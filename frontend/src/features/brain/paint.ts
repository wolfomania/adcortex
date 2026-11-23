// Colors the cortex from the quantized brain frames (docs/api.md, "Brain frames").
//
// Each vertex shows the anatomy (light gyri, dark sulci) until its response
// leaves the average band; from there the response color fades in: warm above
// the reference average, cool below it.
import type { BrainFrames } from '@/api/types'

/** Linear RGB, 0–1 per channel. */
export type Rgb = readonly [number, number, number]

export interface BrainPalette {
  positive: Rgb
  negative: Rgb
  gyrus: Rgb
  sulcus: Rgb
  medialWall: Rgb
}

/** |z| up to SHOW_Z shows anatomy only; from FULL_Z the response color is opaque. */
export const SHOW_Z = 0.5
export const FULL_Z = 1.5

type Range = Pick<BrainFrames, 'vmin' | 'vmax'>

export function byteToZ(byte: number, range: Range): number {
  return range.vmin + (byte / 255) * (range.vmax - range.vmin)
}

function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = Math.min(Math.max((x - edge0) / (edge1 - edge0), 0), 1)
  return t * t * (3 - 2 * t)
}

/** RGBA per byte value: the response color and how much of it covers the anatomy. */
export function buildLut(range: Range, palette: BrainPalette): Float32Array {
  const lut = new Float32Array(256 * 4)
  for (let byte = 0; byte < 256; byte++) {
    const z = byteToZ(byte, range)
    const [r, g, b] = z >= 0 ? palette.positive : palette.negative
    lut.set([r, g, b, smoothstep(SHOW_Z, FULL_Z, Math.abs(z))], byte * 4)
  }
  return lut
}

/** Anatomy colors, 3 floats per vertex: sulcal depth shading; the medial wall flat. */
export function buildBase(
  sulc: Uint8Array,
  parcel: Uint8Array,
  palette: BrainPalette,
): Float32Array {
  const base = new Float32Array(sulc.length * 3)
  for (let v = 0; v < sulc.length; v++) {
    const depth = (sulc[v] ?? 0) / 255
    for (let channel = 0; channel < 3; channel++) {
      base[v * 3 + channel] =
        parcel[v] === 0
          ? (palette.medialWall[channel] ?? 0)
          : (palette.gyrus[channel] ?? 0) +
            ((palette.sulcus[channel] ?? 0) - (palette.gyrus[channel] ?? 0)) * depth
    }
  }
  return base
}

export interface FrameSet {
  /** n_frames × n_vertices bytes, row-major. */
  bytes: Uint8Array
  nFrames: number
  nVertices: number
}

/** Frame k covers second [k, k+1); between frame centers the bytes blend linearly. */
export function framePosition(
  time: number,
  nFrames: number,
): { k: number; next: number; f: number } {
  const position = Math.min(Math.max(time - 0.5, 0), Math.max(nFrames - 1, 0))
  const k = Math.floor(position)
  return { k, next: Math.min(k + 1, nFrames - 1), f: position - k }
}

/** Writes the cortex colors at `time` seconds into `out` (3 floats per vertex). */
export function paintFrame(
  out: Float32Array,
  base: Float32Array,
  parcel: Uint8Array,
  frames: FrameSet,
  lut: Float32Array,
  time: number,
): void {
  const { bytes, nFrames, nVertices } = frames
  const { k, next, f } = framePosition(time, nFrames)
  const from = k * nVertices
  const to = next * nVertices
  for (let v = 0; v < nVertices; v++) {
    const o = v * 3
    const r0 = base[o] ?? 0
    const g0 = base[o + 1] ?? 0
    const b0 = base[o + 2] ?? 0
    if (parcel[v] === 0) {
      out[o] = r0
      out[o + 1] = g0
      out[o + 2] = b0
      continue
    }
    const byte = Math.round((bytes[from + v] ?? 128) * (1 - f) + (bytes[to + v] ?? 128) * f)
    const l = byte * 4
    const alpha = lut[l + 3] ?? 0
    out[o] = r0 + ((lut[l] ?? 0) - r0) * alpha
    out[o + 1] = g0 + ((lut[l + 1] ?? 0) - g0) * alpha
    out[o + 2] = b0 + ((lut[l + 2] ?? 0) - b0) * alpha
  }
}
