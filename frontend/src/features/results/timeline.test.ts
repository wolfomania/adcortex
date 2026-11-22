import { describe, expect, it } from 'vitest'

import { Playback } from './playback'
import { heatFill, mean, meanCurve, timeAtX, timeTicks } from './timeline'

describe('timeline helpers', () => {
  it('colors cells by direction and strength', () => {
    expect(heatFill(2.5)).toBe('color-mix(in oklch, var(--viz-pos) 100%, var(--viz-mid))')
    expect(heatFill(-1)).toBe('color-mix(in oklch, var(--viz-neg) 50%, var(--viz-mid))')
    expect(heatFill(null)).toBe('var(--surface-sunken)')
  })

  it('maps pointer positions to clamped times', () => {
    expect(timeAtX(150, 100, 200, 30)).toBe(7.5)
    expect(timeAtX(50, 100, 200, 30)).toBe(0)
    expect(timeAtX(400, 100, 200, 30)).toBe(30)
  })

  it('picks readable tick steps', () => {
    expect(timeTicks(8)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8])
    expect(timeTicks(30)).toEqual([0, 5, 10, 15, 20, 25, 30])
    expect(timeTicks(180)).toEqual([0, 30, 60, 90, 120, 150, 180])
    // A phone-width track has room for fewer labels.
    expect(timeTicks(30, 3)).toEqual([0, 10, 20, 30])
  })

  it('averages present values only', () => {
    expect(mean([1, null, 3])).toBe(2)
    expect(mean([null])).toBeNull()
  })
})

describe('playback', () => {
  it('clamps reports, notifies listeners, and moves the media on seek', () => {
    const playback = new Playback(10)
    const heard: number[] = []
    const moved: number[] = []
    playback.subscribe(() => heard.push(playback.time))
    const detach = playback.attach((seconds) => moved.push(seconds))

    playback.report(4)
    playback.report(4)
    playback.seek(12)
    detach()
    playback.seek(1)

    expect(heard).toEqual([4, 10, 1])
    expect(moved).toEqual([10])
  })
})

describe('meanCurve', () => {
  it('averages the applicable systems per second', () => {
    const systems = [
      { values: [1, 2, null] },
      { values: [3, null, null] },
      { applicable: false, values: [100, 100, 100] },
    ]

    expect(meanCurve(systems, 3)).toEqual([2, 2, null])
  })
})
