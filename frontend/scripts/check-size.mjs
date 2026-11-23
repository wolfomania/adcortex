// Check the gzip size of the JavaScript the upload route ("/") loads first.
//
// Run after `pnpm build`. The upload route loads the entry chunk, the chunks
// it imports statically, and the code-split chunks of src/routes/index.tsx.
// Everything else (results, 3D brain, charts, export) loads on demand.
import { readFileSync } from 'node:fs'
import { gzipSync } from 'node:zlib'

export const BUDGET_BYTES = 150_000
const DIST = new URL('../dist/', import.meta.url)

/**
 * Manifest keys of the JS chunks needed before the route can render:
 * the entry, the route's split chunks, and their static imports.
 */
export function initialChunkKeys(manifest, routePattern) {
  const roots = Object.keys(manifest).filter(
    (key) => manifest[key].isEntry || routePattern.test(key),
  )
  const seen = new Set()
  const stack = [...roots]
  while (stack.length > 0) {
    const key = stack.pop()
    if (seen.has(key) || !(key in manifest)) {
      continue
    }
    seen.add(key)
    stack.push(...(manifest[key].imports ?? []))
  }
  return [...seen].filter((key) => manifest[key].file.endsWith('.js')).sort()
}

export function gzipSize(buffer) {
  return gzipSync(buffer, { level: 9 }).length
}

function formatKb(bytes) {
  return `${(bytes / 1000).toFixed(1)} kB`
}

function main() {
  const manifest = JSON.parse(readFileSync(new URL('.vite/manifest.json', DIST), 'utf8'))
  const keys = initialChunkKeys(manifest, /src\/routes\/index\.tsx/)
  const rows = keys.map((key) => {
    const file = manifest[key].file
    return { file, gzip: gzipSize(readFileSync(new URL(file, DIST))) }
  })
  const total = rows.reduce((sum, row) => sum + row.gzip, 0)
  for (const row of rows.sort((a, b) => b.gzip - a.gzip)) {
    console.log(`${formatKb(row.gzip).padStart(10)}  ${row.file}`)
  }
  const verdict = total <= BUDGET_BYTES ? 'OK' : 'OVER BUDGET'
  console.log(`\nUpload route initial JS: ${formatKb(total)} gzip`)
  console.log(`Budget: ${formatKb(BUDGET_BYTES)} gzip -> ${verdict}`)
  if (total > BUDGET_BYTES) {
    process.exitCode = 1
  }
}

const isMain = import.meta.url === `file://${process.argv[1]}`
if (isMain) {
  main()
}
