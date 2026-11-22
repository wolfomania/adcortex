import { describe, expect, it, vi } from 'vitest'

import { supportsWebGL } from './webgl'

describe('supportsWebGL', () => {
  it('needs a WebGL context', () => {
    const getContext = vi.spyOn(HTMLCanvasElement.prototype, 'getContext')

    getContext.mockReturnValue(null)
    expect(supportsWebGL()).toBe(false)

    getContext.mockReturnValue({} as RenderingContext)
    expect(supportsWebGL()).toBe(true)

    getContext.mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(supportsWebGL()).toBe(false)
  })
})
