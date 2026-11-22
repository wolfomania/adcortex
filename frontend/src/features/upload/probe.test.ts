import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { probeDuration } from './probe'

describe('probeDuration', () => {
  let element: HTMLMediaElement | undefined

  beforeEach(() => {
    Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:clip'), revokeObjectURL: vi.fn() })
    vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {})
    const create = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const created = create(tag)
      if (created instanceof HTMLMediaElement) {
        element = created
      }
      return created
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    element = undefined
  })

  it('reads the duration from the metadata', async () => {
    const probing = probeDuration(new File(['x'], 'a.mp4'), 'video')
    Object.defineProperty(element, 'duration', { value: 12.5 })
    element?.dispatchEvent(new Event('loadedmetadata'))

    await expect(probing).resolves.toBe(12.5)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:clip')
  })

  it('gives up on files the browser cannot decode', async () => {
    const probing = probeDuration(new File(['x'], 'a.wav'), 'audio')
    element?.dispatchEvent(new Event('error'))

    await expect(probing).resolves.toBeNull()
  })

  it('gives up after a while', async () => {
    vi.useFakeTimers()
    const probing = probeDuration(new File(['x'], 'a.mkv'), 'video')
    vi.advanceTimersByTime(10_000)

    await expect(probing).resolves.toBeNull()
  })
})
