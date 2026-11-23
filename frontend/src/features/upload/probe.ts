// Read a media file's duration in the browser before uploading it.

const PROBE_TIMEOUT_MS = 8000

/**
 * Duration in seconds, or null when the browser cannot decode the file
 * (the server probes it anyway, so null never blocks an upload).
 */
export function probeDuration(file: File, kind: 'video' | 'audio'): Promise<number | null> {
  return new Promise((resolve) => {
    const element = document.createElement(kind)
    const url = URL.createObjectURL(file)
    let settled = false
    const finish = (value: number | null) => {
      if (settled) {
        return
      }
      settled = true
      clearTimeout(timer)
      element.removeAttribute('src')
      element.load()
      URL.revokeObjectURL(url)
      resolve(value)
    }
    const timer = setTimeout(() => finish(null), PROBE_TIMEOUT_MS)
    element.preload = 'metadata'
    element.muted = true
    element.addEventListener('loadedmetadata', () => {
      const { duration } = element
      finish(Number.isFinite(duration) && duration > 0 ? duration : null)
    })
    element.addEventListener('error', () => finish(null))
    element.src = url
  })
}
