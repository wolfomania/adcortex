// A tiny toast queue. Components call `toast()`; <Toaster/> renders the queue.
export type ToastTone = 'default' | 'success' | 'error'

export interface ToastAction {
  label: string
  onClick: () => void
}

export interface Toast {
  id: number
  title: string
  description?: string
  tone: ToastTone
  action?: ToastAction
}

export type ToastInput = Omit<Toast, 'id' | 'tone'> & { tone?: ToastTone; durationMs?: number }

const DEFAULT_DURATION_MS = 5000
const MAX_TOASTS = 3

type Listener = () => void

let toasts: readonly Toast[] = []
let nextId = 1
const listeners = new Set<Listener>()
const timers = new Map<number, ReturnType<typeof setTimeout>>()

function emit(next: readonly Toast[]): void {
  toasts = next
  for (const listener of listeners) {
    listener()
  }
}

export function subscribeToasts(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function getToasts(): readonly Toast[] {
  return toasts
}

export function dismissToast(id: number): void {
  const timer = timers.get(id)
  if (timer) {
    clearTimeout(timer)
    timers.delete(id)
  }
  emit(toasts.filter((t) => t.id !== id))
}

/** Show a toast; returns its id. Errors stay twice as long. */
export function toast(input: ToastInput): number {
  const id = nextId
  nextId += 1
  const { durationMs, tone = 'default', ...rest } = input
  const item: Toast = { id, tone, ...rest }
  const kept = toasts.slice(-(MAX_TOASTS - 1))
  for (const dropped of toasts.filter((t) => !kept.includes(t))) {
    dismissToast(dropped.id)
  }
  emit([...kept, item])
  const lifetime = durationMs ?? (tone === 'error' ? 2 * DEFAULT_DURATION_MS : DEFAULT_DURATION_MS)
  timers.set(
    id,
    setTimeout(() => dismissToast(id), lifetime),
  )
  return id
}

/** Remove every toast (tests and page changes). */
export function clearToasts(): void {
  for (const timer of timers.values()) {
    clearTimeout(timer)
  }
  timers.clear()
  emit([])
}
