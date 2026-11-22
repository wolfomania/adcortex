import { describe, expect, it } from 'vitest'

import { buildBase, buildLut, byteToZ, framePosition, paintFrame, type BrainPalette } from './paint'

const PALETTE: BrainPalette = {
  positive: [1, 0, 0],
  negative: [0, 0, 1],
  gyrus: [0.6, 0.6, 0.6],
  sulcus: [0.2, 0.2, 0.2],
  medialWall: [0.1, 0.1, 0.1],
}
const RANGE = { vmin: -3, vmax: 3 }

describe('brain colors', () => {
  it('maps bytes back to z-scores', () => {
    expect(byteToZ(0, RANGE)).toBe(-3)
    expect(byteToZ(255, RANGE)).toBe(3)
    expect(byteToZ(128, RANGE)).toBeCloseTo(0.01, 2)
  })

  it('shows anatomy near the average and full color far from it', () => {
    const lut = buildLut(RANGE, PALETTE)

    expect(lut[128 * 4 + 3]).toBe(0)
    expect(Array.from(lut.slice(255 * 4, 256 * 4))).toEqual([1, 0, 0, 1])
    expect(Array.from(lut.slice(0, 4))).toEqual([0, 0, 1, 1])
  })

  it('shades sulci darker than gyri and flattens the medial wall', () => {
    const base = buildBase(new Uint8Array([0, 255, 0]), new Uint8Array([1, 1, 0]), PALETTE)

    expect(base[0]).toBeCloseTo(0.6)
    expect(base[3]).toBeCloseTo(0.2)
    expect(base[6]).toBeCloseTo(0.1)
  })

  it('blends frames between second centers', () => {
    expect(framePosition(0, 3)).toEqual({ k: 0, next: 1, f: 0 })
    expect(framePosition(1.5, 3)).toEqual({ k: 1, next: 2, f: 0 })
    expect(framePosition(1, 3)).toEqual({ k: 0, next: 1, f: 0.5 })
    expect(framePosition(99, 3)).toEqual({ k: 2, next: 2, f: 0 })
  })

  it('paints responses over the anatomy and leaves the medial wall alone', () => {
    const parcel = new Uint8Array([1, 0])
    const base = buildBase(new Uint8Array([0, 0]), parcel, PALETTE)
    const frames = { bytes: new Uint8Array([255, 255]), nFrames: 1, nVertices: 2 }
    const out = new Float32Array(6)

    paintFrame(out, base, parcel, frames, buildLut(RANGE, PALETTE), 0.5)

    expect(Array.from(out.slice(0, 3))).toEqual([1, 0, 0])
    expect(Array.from(out.slice(3, 6)).map((c) => Number(c.toFixed(2)))).toEqual([0.1, 0.1, 0.1])
  })
})
