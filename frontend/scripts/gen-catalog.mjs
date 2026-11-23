// Copy the brain-system catalog from the backend into the app.
//
// The API returns system ids, labels, and confidence with every result, but
// not the descriptions, parcels, or citations that explain them. Until the
// API exposes the catalog, the app ships this generated copy of
// backend/src/adcortex/data/systems.yaml. Refresh it with
// `pnpm gen:catalog`.
import { readFile, writeFile } from 'node:fs/promises'

import { parse } from 'yaml'

const SOURCE = new URL('../../backend/src/adcortex/data/systems.yaml', import.meta.url)
const OUTPUT = new URL('../src/features/systems/catalog.json', import.meta.url)

/** Reduce the YAML document to what the UI shows. */
export function toCatalog(doc) {
  const citations = doc.citations ?? {}
  return {
    version: doc.version,
    systems: doc.systems.map((system) => ({
      id: system.id,
      label: system.label,
      confidence: system.confidence,
      visual: Boolean(system.visual),
      parcels: system.parcels.map(String),
      description: system.description.trim(),
      citations: (system.citations ?? []).map((key) => {
        if (!(key in citations)) {
          throw new Error(`Unknown citation "${key}" in system "${system.id}"`)
        }
        return { key, text: citations[key].trim() }
      }),
    })),
  }
}

const isMain = import.meta.url === `file://${process.argv[1]}`
if (isMain) {
  const doc = parse(await readFile(SOURCE, 'utf8'))
  await writeFile(OUTPUT, `${JSON.stringify(toCatalog(doc), null, 2)}\n`)
  console.log(`Wrote ${OUTPUT.pathname}`)
}
