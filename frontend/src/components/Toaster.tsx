import { CircleAlert, CircleCheck, Info, X } from 'lucide-react'
import { useSyncExternalStore } from 'react'

import { cn } from '@/lib/utils'

import { dismissToast, getToasts, subscribeToasts, type ToastTone } from './toast-store'

const ICONS: Record<ToastTone, typeof Info> = {
  default: Info,
  success: CircleCheck,
  error: CircleAlert,
}

const ICON_CLASS: Record<ToastTone, string> = {
  default: 'text-primary',
  success: 'text-status-good',
  error: 'text-destructive',
}

/** Renders the toast queue in a polite live region, bottom right. */
export function Toaster() {
  const toasts = useSyncExternalStore(subscribeToasts, getToasts, getToasts)
  return (
    <section
      aria-label="Notifications"
      aria-live="polite"
      className="no-print pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col items-end gap-2 sm:left-auto sm:w-96"
    >
      {toasts.map((item) => {
        const Icon = ICONS[item.tone]
        return (
          <div
            key={item.id}
            role={item.tone === 'error' ? 'alert' : 'status'}
            className="pointer-events-auto flex w-full animate-in items-start gap-3 rounded-lg border border-border bg-popover p-3 text-sm text-popover-foreground shadow-lg shadow-black/30 fade-in slide-in-from-bottom-2"
          >
            <Icon aria-hidden className={cn('mt-0.5 size-4 shrink-0', ICON_CLASS[item.tone])} />
            <div className="min-w-0 flex-1">
              <p className="font-medium">{item.title}</p>
              {item.description ? (
                <p className="mt-0.5 text-muted-foreground">{item.description}</p>
              ) : null}
              {item.action ? (
                <button
                  type="button"
                  className="mt-2 text-sm font-medium text-primary underline-offset-4 hover:underline"
                  onClick={() => {
                    item.action?.onClick()
                    dismissToast(item.id)
                  }}
                >
                  {item.action.label}
                </button>
              ) : null}
            </div>
            <button
              type="button"
              aria-label="Dismiss notification"
              className="-m-1 rounded p-1 text-muted-foreground hover:text-foreground"
              onClick={() => dismissToast(item.id)}
            >
              <X aria-hidden className="size-4" />
            </button>
          </div>
        )
      })}
    </section>
  )
}
