import { useQuery } from '@tanstack/react-query'
import { FlaskConical } from 'lucide-react'

import { configQuery } from '@/api/queries'
import type { AppConfig } from '@/api/types'

const MESSAGES: Record<Exclude<AppConfig['brain_backend'], 'tribe'>, string> = {
  mock: 'Demo mode: brain responses are synthetic, not predicted by TRIBE v2.',
  replay: 'Demo mode: brain responses are replayed from a stored run, not predicted for your file.',
}

/** A strip under the header when the backend serves demo brain data. */
export function DemoBanner() {
  const { data: config } = useQuery(configQuery())
  const backend = config?.brain_backend
  if (!backend || backend === 'tribe') {
    return null
  }
  return (
    <div
      role="note"
      className="border-b border-status-warning/25 bg-status-warning/10 text-sm text-foreground"
    >
      <div className="mx-auto flex max-w-7xl items-center gap-2 px-4 py-2 sm:px-6">
        <FlaskConical aria-hidden className="size-4 shrink-0 text-status-warning" />
        <span>{MESSAGES[backend]}</span>
      </div>
    </div>
  )
}
