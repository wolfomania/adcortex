import { describe, expect, it } from 'vitest'

import { toggleSelection } from './selection'

describe('toggleSelection', () => {
  it('adds, removes, and keeps the two latest picks', () => {
    expect(toggleSelection([], 'a')).toEqual(['a'])
    expect(toggleSelection(['a'], 'b')).toEqual(['a', 'b'])
    expect(toggleSelection(['a', 'b'], 'c')).toEqual(['b', 'c'])
    expect(toggleSelection(['a', 'b'], 'a')).toEqual(['b'])
  })
})
