// A small multipart/form-data parser. Browsers parse uploads with
// `Request.formData()`; under jsdom that call rejects bodies with files, so
// the mock backend falls back to this.

const CRLF = '\r\n'
const HEADER_END = '\r\n\r\n'

function boundaryOf(contentType: string | null): string {
  const match = /boundary=(?:"([^"]+)"|([^;]+))/i.exec(contentType ?? '')
  const boundary = match?.[1] ?? match?.[2]
  if (!boundary) {
    throw new Error('The multipart body has no boundary.')
  }
  return boundary
}

function headerValue(headers: string, name: string): string | null {
  const line = headers.split(CRLF).find((h) => h.toLowerCase().startsWith(`${name}:`))
  return line ? line.slice(name.length + 1).trim() : null
}

/**
 * Parse a multipart body. The text view (one character per byte) finds the
 * part boundaries; file contents are sliced from the original bytes.
 */
export function parseMultipart(body: ArrayBuffer, contentType: string | null): FormData {
  const delimiter = `--${boundaryOf(contentType)}`
  const bytes = new Uint8Array(body)
  const text = Array.from(bytes, (b) => String.fromCharCode(b)).join('')
  const form = new FormData()
  let cursor = text.indexOf(delimiter)
  while (cursor >= 0) {
    const start = cursor + delimiter.length
    if (text.startsWith('--', start)) {
      break
    }
    const next = text.indexOf(delimiter, start)
    const end = next < 0 ? text.length : next
    const headerEnd = text.indexOf(HEADER_END, start)
    if (headerEnd >= 0 && headerEnd < end) {
      const headers = text.slice(start + CRLF.length, headerEnd)
      const contentStart = headerEnd + HEADER_END.length
      const contentEnd = Math.max(contentStart, end - CRLF.length)
      appendPart(form, headers, bytes, [contentStart, contentEnd])
    }
    cursor = next
  }
  return form
}

function appendPart(
  form: FormData,
  headers: string,
  bytes: Uint8Array,
  [from, to]: [number, number],
): void {
  const disposition = headerValue(headers, 'content-disposition') ?? ''
  const name = /name="([^"]*)"/.exec(disposition)?.[1]
  const filename = /filename="([^"]*)"/.exec(disposition)?.[1]
  if (!name) {
    return
  }
  if (filename === undefined) {
    form.append(name, new TextDecoder().decode(bytes.slice(from, to)))
    return
  }
  const type = headerValue(headers, 'content-type') ?? 'application/octet-stream'
  form.append(name, new File([bytes.slice(from, to)], filename, { type }), filename)
}
