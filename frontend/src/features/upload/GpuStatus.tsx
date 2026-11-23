import { cn } from '@/lib/utils'

import type { GpuState } from './useWarmup'

const LABELS: Record<Exclude<GpuState, 'unknown'>, string> = {
  warming: 'GPU starting',
  ready: 'GPU ready',
}

/** A small status pill for the GPU worker the page warms up. */
export function GpuStatus({ state }: { state: GpuState }) {
  if (state === 'unknown') {
    return null
  }
  return (
    <span
      role="status"
      title={
        state === 'warming'
          ? 'The GPU worker is starting now, so your analysis will not wait for it.'
          : 'A GPU worker is running and ready.'
      }
      className="inline-flex items-center gap-2 rounded-full border border-border bg-sunken px-2.5 py-1 font-mono text-[11px] tracking-wide text-muted-foreground uppercase"
    >
      <span
        aria-hidden
        className={cn(
          'size-1.5 rounded-full',
          state === 'warming' ? 'animate-pulse bg-status-warning' : 'bg-status-good',
        )}
      />
      {LABELS[state]}
    </span>
  )
}
