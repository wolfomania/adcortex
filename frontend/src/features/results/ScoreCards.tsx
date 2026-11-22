// The headline numbers, each with what it measures.
import type { AnalysisResult } from '@/api/types'

interface Card {
  label: string
  value: string
  unit?: string
  hint: string
}

function cards(result: AnalysisResult): Card[] {
  const { scores } = result
  const score = (value: number | null) => (value === null ? '–' : String(Math.round(value)))
  return [
    {
      label: 'Response index',
      value: score(scores.response_index),
      unit: '/100',
      hint: 'Average percentile of the applicable brain systems against the reference ads.',
    },
    {
      label: 'Hook',
      value: score(scores.hook),
      unit: '/100',
      hint: 'Percentile of the response in the first 3 seconds.',
    },
    {
      label: 'Sustain',
      value: score(scores.sustain),
      unit: scores.sustain === null ? undefined : '%',
      hint: 'Share of seconds with the response above the reference average.',
    },
    {
      label: 'Peaks',
      value: String(scores.peak_count),
      hint: 'Moments where a system rises well above its usual level.',
    },
  ]
}

export function ScoreCards({ result }: { result: AnalysisResult }) {
  const baseline = result.baseline
  return (
    <section aria-label="Scores" className="flex flex-col gap-2">
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {cards(result).map((card) => (
          <div key={card.label} className="rounded-lg border bg-card p-4">
            <dt className="text-xs font-medium text-muted-foreground">{card.label}</dt>
            <dd className="mt-1 flex items-baseline gap-1">
              <span className="font-mono text-3xl font-semibold tabular-nums">{card.value}</span>
              {card.unit ? (
                <span className="text-sm text-muted-foreground">{card.unit}</span>
              ) : null}
            </dd>
            <p className="mt-2 text-xs text-muted-foreground">{card.hint}</p>
          </div>
        ))}
      </dl>
      <p className="text-xs text-muted-foreground">
        {baseline
          ? `Reference: ${baseline.n_clips} ads (${baseline.description}).`
          : 'No reference library is installed, so the scores and percentiles are unavailable.'}
      </p>
    </section>
  )
}
