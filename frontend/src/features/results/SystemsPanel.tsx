// The ten brain systems: average response, percentiles, and what each one is.
import type { SystemSeries } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { CONFIDENCE_HINTS, CONFIDENCE_LABELS, systemInfo } from '@/features/systems/catalog'
import { formatPercentile, formatZ } from '@/lib/format'
import { cn } from '@/lib/utils'

const BAR_Z = 2

function MeanBar({ z }: { z: number }) {
  const width = Math.min(Math.abs(z) / BAR_Z, 1) * 50
  return (
    <div className="relative h-1.5 w-full rounded-full bg-muted" aria-hidden>
      <div className="absolute inset-y-0 left-1/2 w-px bg-viz-axis" />
      <div
        className={cn('absolute inset-y-0 rounded-full', z >= 0 ? 'bg-viz-pos' : 'bg-viz-neg')}
        style={z >= 0 ? { left: '50%', width: `${width}%` } : { right: '50%', width: `${width}%` }}
      />
    </div>
  )
}

function order(systems: readonly SystemSeries[]): SystemSeries[] {
  return [...systems].sort(
    (a, b) =>
      Number(b.applicable !== false) - Number(a.applicable !== false) || b.mean_z - a.mean_z,
  )
}

/** Where the system's mean falls among the reference ads and the user's own analyses. */
function Ranks({ system }: { system: SystemSeries }) {
  const ranks = [
    system.percentile == null ? null : `${formatPercentile(system.percentile)} vs reference`,
    system.library_percentile == null
      ? null
      : `${formatPercentile(system.library_percentile)} vs your library`,
  ].filter((rank) => rank !== null)
  return ranks.length ? <span>{ranks.join(' · ')}</span> : null
}

export function SystemsPanel({ systems }: { systems: readonly SystemSeries[] }) {
  return (
    <section aria-labelledby="systems-title" className="flex flex-col gap-3">
      <h2 id="systems-title" className="text-sm font-medium">
        Brain systems
      </h2>
      <ul className="flex flex-col divide-y rounded-lg border bg-card">
        {order(systems).map((system) => {
          const info = systemInfo(system.id)
          const applicable = system.applicable !== false
          return (
            <li key={system.id} className={cn('px-4 py-3', !applicable && 'opacity-60')}>
              <details className="group">
                <summary className="flex cursor-pointer list-none flex-col gap-2 [&::-webkit-details-marker]:hidden">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium">{system.label}</span>
                    <span className="font-mono text-xs tabular-nums">
                      {applicable ? formatZ(system.mean_z) : 'needs a picture'}
                    </span>
                  </div>
                  {applicable ? <MeanBar z={system.mean_z} /> : null}
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <Badge variant="outline" title={CONFIDENCE_HINTS[system.confidence]}>
                      {CONFIDENCE_LABELS[system.confidence]}
                    </Badge>
                    {applicable ? <Ranks system={system} /> : null}
                  </div>
                </summary>
                {info ? (
                  <div className="mt-3 flex flex-col gap-2 text-xs text-muted-foreground">
                    <p className="text-sm text-foreground">{info.description}</p>
                    <p>Regions (HCP-MMP1): {info.parcels.join(', ')}</p>
                    <ul className="flex list-disc flex-col gap-1 pl-4">
                      {info.citations.map((citation) => (
                        <li key={citation.key}>{citation.text}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </details>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
