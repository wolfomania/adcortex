// The headline numbers, each with what it measures.
import type { AnalysisResult } from '@/api/types'

import { referenceNote, scoreCards } from './describe'

export function ScoreCards({ result }: { result: AnalysisResult }) {
  return (
    <section aria-label="Scores" className="flex flex-col gap-2">
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {scoreCards(result).map((card) => (
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
      <p className="text-xs text-muted-foreground">{referenceNote(result)}</p>
    </section>
  )
}
