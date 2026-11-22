// Two analyses side by side: scores, the response over time, and each system.
import { curveMonotoneX, line } from 'd3-shape'
import { useMemo } from 'react'

import type { AnalysisResult, SystemSeries } from '@/api/types'
import { FULL_BAR_Z, LEVEL_LABELS, systemLevel } from '@/features/results/describe'
import { meanCurve, timeTicks } from '@/features/results/timeline'
import { formatClock, formatZ } from '@/lib/format'
import { cn } from '@/lib/utils'

import { formatDelta, pairSystems, scoreRows, zExtent } from './compare'

export interface Named {
  name: string
  result: AnalysisResult
}

export function Swatch({ side }: { side: 'a' | 'b' }) {
  return (
    <span
      className={cn(
        'inline-block size-2.5 shrink-0 rounded-full',
        side === 'a' ? 'bg-viz-a' : 'bg-viz-b',
      )}
      aria-hidden
    />
  )
}

export function ScoreComparison({ a, b }: { a: Named; b: Named }) {
  const value = (n: number | null, unit: string) => (n === null ? '–' : `${Math.round(n)}${unit}`)
  return (
    <section aria-labelledby="scores-title" className="flex flex-col gap-3">
      <h2 id="scores-title" className="text-sm font-medium">
        Scores
      </h2>
      <div className="overflow-x-auto rounded-lg border bg-card">
        <table className="w-full text-sm" aria-labelledby="scores-title">
          <thead className="text-xs text-muted-foreground">
            <tr className="border-b">
              <th scope="col" className="px-4 py-2 text-left font-medium">
                Score
              </th>
              <th scope="col" className="px-4 py-2 text-right font-medium">
                <span className="inline-flex items-center gap-1.5">
                  <Swatch side="a" />A
                </span>
              </th>
              <th scope="col" className="px-4 py-2 text-right font-medium">
                <span className="inline-flex items-center gap-1.5">
                  <Swatch side="b" />B
                </span>
              </th>
              <th scope="col" className="px-4 py-2 text-right font-medium">
                B − A
              </th>
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {scoreRows(a.result, b.result).map((row) => (
              <tr key={row.label} className="border-b last:border-0">
                <th scope="row" className="px-4 py-2 text-left font-sans font-normal">
                  {row.label}
                </th>
                <td className="px-4 py-2 text-right">{value(row.a, row.unit)}</td>
                <td className="px-4 py-2 text-right">{value(row.b, row.unit)}</td>
                <td className="px-4 py-2 text-right text-muted-foreground">
                  {formatDelta(row.a, row.b)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

const CHART_W = 1000
const CHART_H = 220

export function ResponseChart({ a, b }: { a: Named; b: Named }) {
  const { paths, extent, duration } = useMemo(() => {
    const curves = [a.result, b.result].map((result) =>
      meanCurve(result.systems, result.times.length),
    )
    const span = Math.max(a.result.duration_s, b.result.duration_s, 1)
    const range = zExtent(curves)
    const draw = line<number | null>()
      .defined((value) => value !== null)
      .x((_, k) => ((k + 0.5) / span) * CHART_W)
      .y((value) => CHART_H / 2 - ((value ?? 0) / range) * (CHART_H / 2))
      .curve(curveMonotoneX)
    return { paths: curves.map((curve) => draw(curve) ?? ''), extent: range, duration: span }
  }, [a.result, b.result])

  return (
    <section aria-labelledby="response-title" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="response-title" className="text-sm font-medium">
          Response over time
        </h2>
        <p className="text-xs text-muted-foreground">Mean z-score of the applicable systems</p>
      </div>
      <div className="grid grid-cols-[3rem_1fr] gap-x-2 rounded-lg border bg-card p-4">
        <div className="relative font-mono text-[0.68rem] text-muted-foreground" aria-hidden>
          <span className="absolute top-0 right-0">{formatZ(extent)}</span>
          <span className="absolute top-1/2 right-0 -translate-y-1/2">0</span>
          <span className="absolute right-0 bottom-0">{formatZ(-extent)}</span>
        </div>
        <svg
          viewBox={`0 0 ${CHART_W} ${CHART_H}`}
          preserveAspectRatio="none"
          className="h-56 w-full overflow-visible"
          role="img"
          aria-label={`Mean response over time: A in one color, B in another, on a scale of ${formatZ(-extent)} to ${formatZ(extent)}`}
        >
          <line
            x1={0}
            x2={CHART_W}
            y1={CHART_H / 2}
            y2={CHART_H / 2}
            className="stroke-viz-axis"
            strokeDasharray="4 4"
            vectorEffect="non-scaling-stroke"
          />
          {paths.map((d, i) => (
            <path
              key={i === 0 ? 'a' : 'b'}
              d={d}
              fill="none"
              strokeWidth={2}
              vectorEffect="non-scaling-stroke"
              className={i === 0 ? 'stroke-viz-a' : 'stroke-viz-b'}
            />
          ))}
        </svg>
        <div />
        <div
          className="relative mt-1 h-4 font-mono text-[0.68rem] text-muted-foreground"
          aria-hidden
        >
          {timeTicks(duration).map((t) => (
            <span
              key={t}
              className="absolute -translate-x-1/2 first:translate-x-0 last:-translate-x-full"
              style={{ left: `${(t / duration) * 100}%` }}
            >
              {formatClock(t)}
            </span>
          ))}
        </div>
      </div>
    </section>
  )
}

interface BarProps {
  system: SystemSeries | undefined
  side: 'a' | 'b'
  hasBaseline: boolean
}

function Bar({ system, side, hasBaseline }: BarProps) {
  if (!system || system.applicable === false) {
    return <span className="text-xs text-muted-foreground">n/a</span>
  }
  const level = systemLevel(system, hasBaseline)
  const width = Math.min(Math.abs(level.z) / FULL_BAR_Z[level.kind], 1) * 50
  const positive = level.z >= 0
  return (
    <span className="flex items-center gap-2">
      <span className="relative h-2 flex-1 rounded-full bg-muted" aria-hidden>
        <span className="absolute inset-y-0 left-1/2 w-px bg-viz-axis" />
        <span
          className={cn('absolute inset-y-0 rounded-full', side === 'a' ? 'bg-viz-a' : 'bg-viz-b')}
          style={
            positive ? { left: '50%', width: `${width}%` } : { right: '50%', width: `${width}%` }
          }
        />
      </span>
      <span className="w-16 text-right font-mono text-xs tabular-nums">{formatZ(level.z)}</span>
    </span>
  )
}

/** What a side's bars show: the mean response, or the strongest second without a reference library. */
function levelLabel(named: Named): string {
  return LEVEL_LABELS[named.result.baseline ? 'mean' : 'peak']
}

export function SystemComparison({ a, b }: { a: Named; b: Named }) {
  return (
    // min-w-0 lets the table scroll inside its frame instead of widening the page.
    <section aria-labelledby="systems-compare-title" className="flex min-w-0 flex-col gap-3">
      <h2 id="systems-compare-title" className="text-sm font-medium">
        Brain systems
      </h2>
      <div className="overflow-x-auto rounded-lg border bg-card">
        <table className="w-full min-w-[32rem] text-sm" aria-labelledby="systems-compare-title">
          <thead className="text-xs text-muted-foreground">
            <tr className="border-b">
              <th scope="col" className="px-4 py-2 text-left font-medium">
                System
              </th>
              <th scope="col" className="px-4 py-2 text-left font-medium">
                <span className="inline-flex items-center gap-1.5">
                  <Swatch side="a" />
                  A, {levelLabel(a)}
                </span>
              </th>
              <th scope="col" className="px-4 py-2 text-left font-medium">
                <span className="inline-flex items-center gap-1.5">
                  <Swatch side="b" />
                  B, {levelLabel(b)}
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {pairSystems(a.result, b.result).map((pair) => (
              <tr key={pair.id} className="border-b last:border-0">
                <th scope="row" className="px-4 py-2 text-left font-normal whitespace-nowrap">
                  {pair.label}
                </th>
                <td className="w-2/5 px-4 py-2">
                  <Bar system={pair.a} side="a" hasBaseline={a.result.baseline != null} />
                </td>
                <td className="w-2/5 px-4 py-2">
                  <Bar system={pair.b} side="b" hasBaseline={b.result.baseline != null} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
