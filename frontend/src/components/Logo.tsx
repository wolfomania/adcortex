import { cn } from '@/lib/utils'

interface LogoProps {
  className?: string
}

/** The app mark: a cortex outline crossed by a response trace. */
export function LogoMark({ className }: LogoProps) {
  return (
    <svg
      viewBox="0 0 32 32"
      aria-hidden
      className={cn('size-7 text-primary', className)}
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path
        d="M16 5.5c-2.2-1.6-5.6-1.3-7.3 1-2.6.3-4.4 2.7-3.9 5.3-1.6 1.5-1.8 4.3-.3 6 .1 2.6 2.4 4.6 5 4.4 1.5 2 4.3 2.6 6.5 1.3"
        strokeWidth="1.6"
        opacity="0.55"
      />
      <path
        d="M16 5.5c2.2-1.6 5.6-1.3 7.3 1 2.6.3 4.4 2.7 3.9 5.3 1.6 1.5 1.8 4.3.3 6-.1 2.6-2.4 4.6-5 4.4-1.5 2-4.3 2.6-6.5 1.3"
        strokeWidth="1.6"
        opacity="0.55"
      />
      <path d="M3 16.5h6l2-4.5 3.2 9 2.6-7 1.9 2.5H29" strokeWidth="2" />
    </svg>
  )
}

/** Mark plus wordmark, for the header. */
export function Logo({ className }: LogoProps) {
  return (
    <span className={cn('flex items-center gap-2.5', className)}>
      <LogoMark />
      {/* Phones show the mark alone; the link carries the name. */}
      <span className="hidden flex-col leading-none sm:flex">
        <span className="text-[15px] font-semibold tracking-tight whitespace-nowrap text-foreground">
          AdCortex
        </span>
        <span className="mt-1 font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
          Brain response lab
        </span>
      </span>
    </span>
  )
}
