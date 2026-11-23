import { describe, expect, it, vi } from 'vitest'

import { readPalette } from './palette'

describe('readPalette', () => {
  it('falls back to built-in colors when the theme cannot be read', () => {
    const palette = readPalette()

    for (const color of Object.values(palette)) {
      expect(color).toHaveLength(3)
      for (const channel of color) {
        expect(channel).toBeGreaterThanOrEqual(0)
        expect(channel).toBeLessThanOrEqual(1)
      }
    }
    expect(palette.positive[0]).toBeGreaterThan(palette.positive[2])
    expect(palette.negative[2]).toBeGreaterThan(palette.negative[0])
  })
})

describe('readPalette with a theme', () => {
  it('reads the response colors from CSS variables', () => {
    document.documentElement.style.setProperty('--viz-pos', 'rgb(255 0 0)')
    const context = {
      fillStyle: '',
      fillRect: () => {},
      getImageData: () => ({ data: new Uint8ClampedArray([255, 0, 0, 255]) }),
    }
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
      context as unknown as CanvasRenderingContext2D,
    )

    expect(readPalette().positive).toEqual([1, 0, 0])
    document.documentElement.style.removeProperty('--viz-pos')
  })
})
