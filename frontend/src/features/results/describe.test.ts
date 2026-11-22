import { describe, expect, it } from 'vitest'

import type { SystemSeries } from '@/api/types'

import { formatLevel, systemLevel } from './describe'

function system(values: (number | null)[], meanZ: number): SystemSeries {
  return { id: 'faces', label: 'Faces', confidence: 'medium', values, mean_z: meanZ }
}

describe('systemLevel', () => {
  it('sums a system up by its mean against a reference library', () => {
    const level = systemLevel(system([0.4, 1.8, null], 1.1), true)

    expect(level).toEqual({ z: 1.1, kind: 'mean' })
    expect(formatLevel(level)).toBe('+1.1 SD')
  })

  it('uses the strongest second when the clip is only compared with itself', () => {
    const level = systemLevel(system([-0.6, 2.84, null, 0.1], 0), false)

    expect(level).toEqual({ z: 2.84, kind: 'peak' })
    expect(formatLevel(level)).toBe('peak +2.8 SD')
  })

  it('reads zero when a system has no values', () => {
    expect(systemLevel(system([null], 0), false)).toEqual({ z: 0, kind: 'peak' })
  })
})
