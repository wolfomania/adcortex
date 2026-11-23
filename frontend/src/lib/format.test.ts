import { describe, expect, it } from 'vitest'

import {
  formatBytes,
  formatClock,
  formatDuration,
  formatPercentile,
  formatRelative,
  formatZ,
  ordinal,
} from './format'

describe('formatClock', () => {
  it('formats seconds as m:ss', () => {
    expect(formatClock(0)).toBe('0:00')
    expect(formatClock(9.99)).toBe('0:09')
    expect(formatClock(75)).toBe('1:15')
  })

  it('adds hours for long media and clamps negatives', () => {
    expect(formatClock(3725)).toBe('1:02:05')
    expect(formatClock(-3)).toBe('0:00')
  })
})

describe('formatDuration', () => {
  it('uses seconds under a minute and minutes above', () => {
    expect(formatDuration(29.6)).toBe('30 s')
    expect(formatDuration(120)).toBe('2 min')
    expect(formatDuration(125)).toBe('2 min 5 s')
  })
})

describe('formatBytes', () => {
  it('picks a unit and keeps one decimal below 10', () => {
    expect(formatBytes(214)).toBe('214 B')
    expect(formatBytes(3_528_044)).toBe('3.4 MB')
    expect(formatBytes(48_213_504)).toBe('46 MB')
    expect(formatBytes(5 * 1024 ** 3)).toBe('5.0 GB')
  })
})

describe('ordinal and formatPercentile', () => {
  it('uses the English suffixes, including the teens', () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 101].map(ordinal)).toEqual([
      '1st',
      '2nd',
      '3rd',
      '4th',
      '11th',
      '12th',
      '13th',
      '21st',
      '22nd',
      '23rd',
      '101st',
    ])
  })

  it('rounds percentiles and shows a dash when missing', () => {
    expect(formatPercentile(84.1)).toBe('84th')
    expect(formatPercentile(null)).toBe('–')
    expect(formatPercentile(undefined)).toBe('–')
  })
})

describe('formatZ', () => {
  it('signs z-scores with a true minus sign', () => {
    expect(formatZ(1.24)).toBe('+1.2 SD')
    expect(formatZ(-0.44)).toBe('−0.4 SD')
    expect(formatZ(0.01)).toBe('±0.0 SD')
    expect(formatZ(2.345, 2)).toBe('+2.35 SD')
  })
})

describe('formatRelative', () => {
  const now = new Date('2026-11-22T12:00:00Z')

  it('describes recent and older times', () => {
    expect(formatRelative('2026-11-22T11:59:40Z', now)).toBe('just now')
    expect(formatRelative('2026-11-22T11:55:00Z', now)).toBe('5 minutes ago')
    expect(formatRelative('2026-11-22T10:25:00Z', now)).toBe('2 hours ago')
    expect(formatRelative('2026-11-21T10:00:00Z', now)).toBe('yesterday')
    expect(formatRelative('2026-11-08T12:00:00Z', now)).toBe('2 weeks ago')
    expect(formatRelative('2024-11-22T12:00:00Z', now)).toBe('2 years ago')
  })
})
