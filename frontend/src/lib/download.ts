// Saving files from the browser.

/** A file name made from free text: lowercase words joined by hyphens. */
export function slugify(text: string, fallback = 'analysis'): string {
  const slug = text
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60)
    .replace(/-+$/, '')
  return slug || fallback
}

/** Saves `data` as pretty-printed JSON under `filename`. */
export function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([`${JSON.stringify(data, null, 2)}\n`], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  // Some browsers start the download after the click returns.
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
