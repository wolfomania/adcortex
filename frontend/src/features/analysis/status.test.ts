import { describe, expect, it } from 'vitest'

import type { Analysis, Status } from '@/api/types'

import { isTerminal, progressFraction, progressMessage, stepState } from './status'

function analysis(status: Status, extra: Partial<Analysis> = {}): Analysis {
  return {
    meta: {} as Analysis['meta'],
    state: { status },
    ...extra,
  }
}

describe('analysis status', () => {
  it('knows the final states', () => {
    expect(isTerminal('completed')).toBe(true)
    expect(isTerminal('failed')).toBe(true)
    expect(isTerminal('predicting')).toBe(false)
    expect(isTerminal(undefined)).toBe(false)
  })

  it('places a stage before, at, or after the current one', () => {
    expect(stepState('queued', 'predicting')).toBe('done')
    expect(stepState('predicting', 'predicting')).toBe('current')
    expect(stepState('analyzing', 'predicting')).toBe('upcoming')
  })

  it('prefers live progress, then the stage position', () => {
    expect(progressFraction(analysis('completed'))).toBe(1)
    expect(
      progressFraction(
        analysis('predicting', { progress: { status: 'predicting', fraction: 1.4 } }),
      ),
    ).toBe(1)
    expect(progressFraction(analysis('preparing'))).toBeCloseTo(1 / 6)
    expect(progressFraction(analysis('failed'))).toBe(0)
  })

  it('prefers the live message, then the stored one, then the stage', () => {
    const live = { status: 'predicting' as const, message: ' 40% of the clip ' }

    expect(progressMessage(analysis('predicting', { progress: live }))).toBe('40% of the clip')
    expect(
      progressMessage(analysis('queued', { state: { status: 'queued', message: 'Waiting.' } })),
    ).toBe('Waiting.')
    expect(progressMessage(analysis('preparing'))).toMatch(/scene cuts/)
    expect(progressMessage(analysis('failed'))).toBe('')
  })
})
