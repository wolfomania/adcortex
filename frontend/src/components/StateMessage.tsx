import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

interface StateMessageProps {
  icon: LucideIcon
  title: string
  children?: ReactNode
  actions?: ReactNode
  tone?: 'default' | 'error'
  className?: string
}

/** A centered message for empty, missing, and failed states. */
export function StateMessage({
  icon: Icon,
  title,
  children,
  actions,
  tone = 'default',
  className,
}: StateMessageProps) {
  return (
    <div
      role={tone === 'error' ? 'alert' : undefined}
      className={cn(
        'mx-auto flex max-w-md flex-col items-center px-6 py-16 text-center',
        className,
      )}
    >
      <span
        className={cn(
          'grid size-12 place-items-center rounded-xl border bg-card',
          tone === 'error'
            ? 'border-destructive/40 text-destructive'
            : 'border-border text-primary',
        )}
      >
        <Icon aria-hidden className="size-5" />
      </span>
      <h2 className="mt-5 text-lg font-semibold tracking-tight">{title}</h2>
      {children ? <div className="mt-2 text-sm text-muted-foreground">{children}</div> : null}
      {actions ? <div className="mt-6 flex flex-wrap justify-center gap-2">{actions}</div> : null}
    </div>
  )
}
