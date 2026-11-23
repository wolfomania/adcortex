import { afterEach, describe, expect, it, vi } from 'vitest'

import { downloadJson, slugify } from './download'

describe('slugify', () => {
  it('keeps plain words and drops the rest', () => {
    expect(slugify('Lumen launch: 30s master')).toBe('lumen-launch-30s-master')
    expect(slugify('Café crème')).toBe('cafe-creme')
    expect(slugify('***')).toBe('analysis')
  })
})

describe('downloadJson', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('clicks a temporary link to a JSON blob', () => {
    const created = vi.fn((_: Blob) => 'blob:result')
    Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    downloadJson('result.json', { a: 1 })

    expect(click).toHaveBeenCalledOnce()
    expect(created.mock.calls[0]?.[0].type).toBe('application/json')
    expect(document.querySelector('a[download]')).toBeNull()
  })
})
