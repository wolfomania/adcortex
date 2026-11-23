import { afterEach, describe, expect, it, vi } from 'vitest'

import { Playback } from '@/features/results/playback'

import { captureBrain, setBrainCanvas } from './snapshot'

function canvasOnScreen(): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  document.body.append(canvas)
  return canvas
}

describe('captureBrain', () => {
  afterEach(() => {
    setBrainCanvas(null)
    document.body.replaceChildren()
  })

  it('returns no pictures when the brain is not on screen', async () => {
    const take = vi.fn(() => 'picture')

    const withoutCanvas = await captureBrain(new Playback(30), [1, 2], take)
    setBrainCanvas(document.createElement('canvas'))
    const detached = await captureBrain(new Playback(30), [1, 2], take)

    expect(withoutCanvas).toEqual([])
    expect(detached).toEqual([])
    expect(take).not.toHaveBeenCalled()
  })

  it('pictures the brain at each time and puts the playhead back', async () => {
    const playback = new Playback(30)
    playback.report(7)
    const seeker = vi.fn()
    playback.attach(seeker)
    setBrainCanvas(canvasOnScreen())

    const pictures = await captureBrain(playback, [1.5, 4.5], () => `at ${playback.time}`)

    expect(pictures).toEqual(['at 1.5', 'at 4.5'])
    expect(playback.time).toBe(7)
    expect(seeker).toHaveBeenLastCalledWith(7)
  })

  it('puts the playhead back when a picture fails', async () => {
    const playback = new Playback(30)
    playback.report(2)
    setBrainCanvas(canvasOnScreen())
    const take = () => {
      throw new Error('The canvas is tainted')
    }

    await expect(captureBrain(playback, [5], take)).rejects.toThrow('The canvas is tainted')
    expect(playback.time).toBe(2)
  })
})
