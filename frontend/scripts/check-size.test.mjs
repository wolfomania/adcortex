import { describe, expect, it } from 'vitest'

import { gzipSize, initialChunkKeys } from './check-size.mjs'

const manifest = {
  'index.html': {
    file: 'assets/index-a.js',
    isEntry: true,
    imports: ['_react-b.js'],
    dynamicImports: ['src/routes/a.$id.tsx?tsr-split=component'],
    css: ['assets/index-a.css'],
  },
  '_react-b.js': { file: 'assets/react-b.js' },
  '_three-c.js': { file: 'assets/three-c.js' },
  '_ui-d.js': { file: 'assets/ui-d.js', imports: ['_react-b.js'] },
  'src/routes/index.tsx?tsr-split=component': {
    file: 'assets/index-e.js',
    isDynamicEntry: true,
    imports: ['_ui-d.js'],
  },
  'src/routes/a.$id.tsx?tsr-split=component': {
    file: 'assets/a._id-f.js',
    isDynamicEntry: true,
    imports: ['_three-c.js'],
  },
  'style.css': { file: 'assets/style.css' },
}

describe('initialChunkKeys', () => {
  it('follows static imports from the entry and the route chunks', () => {
    const keys = initialChunkKeys(manifest, /src\/routes\/index\.tsx/)

    expect(keys).toEqual([
      '_react-b.js',
      '_ui-d.js',
      'index.html',
      'src/routes/index.tsx?tsr-split=component',
    ])
  })

  it('leaves out lazily loaded routes and their dependencies', () => {
    const keys = initialChunkKeys(manifest, /src\/routes\/index\.tsx/)

    expect(keys).not.toContain('_three-c.js')
    expect(keys).not.toContain('src/routes/a.$id.tsx?tsr-split=component')
  })
})

describe('gzipSize', () => {
  it('compresses repetitive content', () => {
    const text = Buffer.from('a'.repeat(10_000))

    expect(gzipSize(text)).toBeLessThan(200)
  })
})
