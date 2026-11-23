// The written report: what the LLM read from the metrics, or why there is none.
import { LoaderCircle, RefreshCw } from 'lucide-react'

import type { Analysis, Report, StoredReport } from '@/api/types'
import { Button } from '@/components/ui/button'
import { formatClock } from '@/lib/format'

import { usePlayback } from './playback'

const INPUTS: Record<StoredReport['input_mode'], string> = {
  video: 'the video, the metrics, and the transcript',
  audio: 'the audio, the metrics, and the transcript',
  keyframes: 'keyframes, the metrics, and the transcript',
  text: 'the metrics and the transcript',
}

function TimeChip({ t }: { t: number }) {
  const playback = usePlayback()
  return (
    <button
      type="button"
      onClick={() => playback.seek(t)}
      className="rounded-md border px-1.5 py-0.5 font-mono text-xs tabular-nums hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
      aria-label={`Play from ${formatClock(t)}`}
    >
      {formatClock(t)}
    </button>
  )
}

function ReportBody({ report }: { report: Report }) {
  return (
    <div className="flex flex-col gap-6">
      <h3 className="text-xl font-semibold tracking-tight text-balance">{report.headline}</h3>
      {report.key_moments.length ? (
        <div className="flex flex-col gap-3">
          <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Key moments
          </h4>
          <ol className="flex flex-col gap-4">
            {report.key_moments.map((moment) => (
              <li key={`${moment.t}-${moment.title}`} className="flex gap-3">
                <TimeChip t={moment.t} />
                <div className="flex flex-col gap-1 text-sm">
                  <span className="font-medium">{moment.title}</span>
                  <span>{moment.what_happens}</span>
                  <span className="text-muted-foreground">{moment.brain_response}</span>
                </div>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
      {report.recommendations.length ? (
        <div className="flex flex-col gap-3">
          <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Recommendations
          </h4>
          <ol className="flex flex-col gap-3">
            {report.recommendations.map((item) => (
              <li key={item.title} className="flex gap-3 text-sm">
                {typeof item.t === 'number' ? <TimeChip t={item.t} /> : null}
                <div className="flex flex-col gap-1">
                  <span className="font-medium">{item.title}</span>
                  <span className="text-muted-foreground">{item.detail}</span>
                </div>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  )
}

export interface ReportPanelProps {
  analysis: Analysis
  report: StoredReport | null | undefined
  /** Rewrites the report; absent on read-only pages. */
  onRewrite?: () => void
  rewriting?: boolean
}

export function ReportPanel({ analysis, report, onRewrite, rewriting = false }: ReportPanelProps) {
  const { status, llm } = analysis.state
  let body: React.ReactNode
  if (status === 'interpreting' || rewriting) {
    body = (
      <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
        <LoaderCircle className="size-4 animate-spin" aria-hidden />
        Writing the report. The metrics are ready meanwhile.
      </p>
    )
  } else if (report) {
    body = <ReportBody report={report.report} />
  } else if (llm?.status === 'failed') {
    body = (
      <p className="text-sm" role="alert">
        Writing the report failed{llm.error ? `: ${llm.error}` : '.'} The metrics are complete.
      </p>
    )
  } else {
    body = (
      <p className="text-sm text-muted-foreground">
        No report model is configured, so this analysis has metrics only.
      </p>
    )
  }
  const canRewrite = onRewrite && status === 'completed' && llm?.status !== 'skipped'

  return (
    <section
      aria-labelledby="report-title"
      className="flex flex-col gap-4 rounded-lg border bg-card p-5"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 id="report-title" className="text-sm font-medium">
          Report
        </h2>
        {canRewrite && !rewriting ? (
          <Button variant="ghost" size="sm" onClick={onRewrite} className="print:hidden">
            <RefreshCw aria-hidden />
            {report ? 'Rewrite' : 'Write the report again'}
          </Button>
        ) : null}
      </div>
      {body}
      {report && status !== 'interpreting' && !rewriting ? (
        <p className="border-t pt-3 text-xs text-muted-foreground">
          Written by {report.model} from {INPUTS[report.input_mode]}. TRIBE v2 predicts an average
          viewer's cortical response; it does not forecast sales or individual reactions.
        </p>
      ) : null}
    </section>
  )
}
