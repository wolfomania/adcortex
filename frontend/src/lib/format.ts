// Formatting for numbers, times, and sizes shown in the app.

/** Media time as `m:ss` (or `h:mm:ss`), for timecodes and axes. */
export function formatClock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds + 1e-6))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = String(total % 60).padStart(2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`
}

/** A duration in words-ish form: `30 s`, `2 min 5 s`. */
export function formatDuration(seconds: number): string {
  const total = Math.round(seconds)
  if (total < 60) {
    return `${total} s`
  }
  const m = Math.floor(total / 60)
  const s = total % 60
  return s === 0 ? `${m} min` : `${m} min ${s} s`
}

const SIZE_UNITS = ['B', 'KB', 'MB', 'GB'] as const

/** File size with one decimal above 10 units: `48 MB`, `3.4 MB`, `214 B`. */
export function formatBytes(bytes: number): string {
  let value = Math.max(0, bytes)
  let unit = 0
  while (value >= 1024 && unit < SIZE_UNITS.length - 1) {
    value /= 1024
    unit += 1
  }
  const digits = unit === 0 || value >= 10 ? 0 : 1
  return `${value.toFixed(digits)} ${SIZE_UNITS[unit]}`
}

/** English ordinal suffix: 1st, 2nd, 3rd, 4th, 11th, 22nd. */
export function ordinal(value: number): string {
  const n = Math.round(value)
  const tens = n % 100
  if (tens >= 11 && tens <= 13) {
    return `${n}th`
  }
  const suffix = ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th'
  return `${n}${suffix}`
}

/** A percentile as an ordinal (`84th`), or an en dash when unknown. */
export function formatPercentile(value: number | null | undefined): string {
  return typeof value === 'number' ? ordinal(value) : '–'
}

/** A z-score with its sign: `+1.2 SD`, `−0.4 SD` (true minus sign). */
export function formatZ(value: number, digits = 1): string {
  const rounded = Number(value.toFixed(digits))
  const sign = rounded > 0 ? '+' : rounded < 0 ? '−' : '±'
  return `${sign}${Math.abs(rounded).toFixed(digits)} SD`
}

const RELATIVE_STEPS: readonly [Intl.RelativeTimeFormatUnit, number][] = [
  ['second', 60],
  ['minute', 60],
  ['hour', 24],
  ['day', 7],
  ['week', 4.35],
  ['month', 12],
  ['year', Number.POSITIVE_INFINITY],
]

const relativeFormat = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

/** `5 minutes ago`, `yesterday`, `last week`. */
export function formatRelative(date: Date | string, now: Date = new Date()): string {
  const then = typeof date === 'string' ? new Date(date) : date
  let value = (then.getTime() - now.getTime()) / 1000
  if (Math.abs(value) < 45) {
    return 'just now'
  }
  for (const [unit, size] of RELATIVE_STEPS) {
    if (Math.abs(value) < size) {
      return relativeFormat.format(Math.round(value), unit)
    }
    value /= size
  }
  return relativeFormat.format(Math.round(value), 'year')
}

const dateTimeFormat = new Intl.DateTimeFormat('en', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

/** `Nov 22, 2026, 10:25 AM` in the viewer's time zone. */
export function formatDateTime(date: Date | string): string {
  return dateTimeFormat.format(typeof date === 'string' ? new Date(date) : date)
}
