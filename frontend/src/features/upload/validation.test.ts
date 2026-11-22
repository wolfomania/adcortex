import { describe, expect, it } from 'vitest'

import type { Limits } from '@/api/types'

import { checkDuration, checkFile, checkScript, defaultName, matchesKind } from './validation'

const LIMITS: Limits = {
  max_duration_s: 120,
  min_duration_s: 2,
  max_upload_mb: 1,
  min_script_chars: 20,
  max_script_chars: 100,
}

function file(name: string, type: string, size = 10) {
  return { name, type, size }
}

describe('upload checks', () => {
  it('accepts media by type, or by extension when the type is missing', () => {
    expect(matchesKind('video', file('a.bin', 'video/mp4'))).toBe(true)
    expect(matchesKind('audio', file('a.mp4', 'video/mp4'))).toBe(true)
    expect(matchesKind('video', file('a.MOV', ''))).toBe(true)
    expect(matchesKind('video', file('a.pdf', 'application/pdf'))).toBe(false)
  })

  it('names the first problem with a file', () => {
    expect(checkFile('video', file('a.mp4', 'video/mp4', 0), LIMITS)).toBe('This file is empty.')
    expect(checkFile('video', file('a.mp3', 'audio/mpeg'), LIMITS)).toMatch(/Audio tab/)
    expect(checkFile('audio', file('a.pdf', 'application/pdf'), LIMITS)).toMatch(/an audio file/)
    expect(checkFile('video', file('a.mp4', 'video/mp4', 2 * 1024 * 1024), LIMITS)).toMatch(
      /the limit is 1 MB/,
    )
    expect(checkFile('video', file('a.mp4', 'video/mp4'), LIMITS)).toBeNull()
  })

  it('checks durations against both limits', () => {
    expect(checkDuration(1, LIMITS)).toMatch(/at least 2 s/)
    expect(checkDuration(200, LIMITS)).toMatch(/the limit is 120 s/)
    expect(checkDuration(30, LIMITS)).toBeNull()
  })

  it('checks script length once there is a script', () => {
    expect(checkScript('   ', LIMITS)).toBeNull()
    expect(checkScript('Too short.', LIMITS)).toMatch(/at least 20/)
    expect(checkScript('x'.repeat(101), LIMITS)).toMatch(/this one has 101/)
    expect(checkScript('A script that is long enough.', LIMITS)).toBeNull()
  })

  it('names analyses after the file or the script', () => {
    expect(defaultName({ file: { name: 'spring_spot.final.mp4' } })).toBe('spring_spot.final')
    expect(defaultName({ script: '  Meet Lumen, the lamp that learns your evenings. ' })).toBe(
      'Meet Lumen, the lamp that learns',
    )
    expect(defaultName({ script: `${'word'.repeat(20)} more` })).toMatch(/\.\.\.$/)
  })
})
