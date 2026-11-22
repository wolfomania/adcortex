import { describe, expect, it } from 'vitest'

import type { Moment } from '@/api/types'

import { pictureMoments } from './exportReport'

function peak(system: string, t: number, z: number): Moment {
  return { kind: 'peak', label: `${system} peak (+${z.toFixed(1)} SD)`, system_id: system, t, z }
}

describe('pictureMoments', () => {
  it('pictures the strongest peaks, apart from each other and in time order', () => {
    const moments: Moment[] = [
      peak('faces', 3, 2.0),
      peak('motion', 3, 2.8),
      // Within two seconds of the stronger peak at 0:03.
      peak('sound', 4, 2.6),
      peak('speech', 12, 2.2),
      { kind: 'dip', label: 'valuation dip (-3.0 SD)', system_id: 'valuation', t: 20, z: -3 },
      peak('salience', 25, 1.9),
      peak('attention', 28, 1.8),
      // A fifth picture would be one too many.
      peak('social', 8, 1.7),
    ]

    expect(pictureMoments(moments)).toEqual([
      { t: 3, peaks: [peak('motion', 3, 2.8), peak('faces', 3, 2.0)] },
      { t: 12, peaks: [peak('speech', 12, 2.2)] },
      { t: 25, peaks: [peak('salience', 25, 1.9)] },
      { t: 28, peaks: [peak('attention', 28, 1.8)] },
    ])
  })

  it('has nothing to picture without peaks', () => {
    expect(pictureMoments([])).toEqual([])
  })
})
