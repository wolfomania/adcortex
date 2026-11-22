// One analysis: the clip and the brain side by side, the systems timeline,
// the report, and the details. Every view follows the same playhead.
import { useMemo } from 'react'

import type { Analysis, AnalysisResult, MediaSource, StoredReport } from '@/api/types'
import { BrainPanel } from '@/features/brain/BrainPanel'
import { formatDateTime, formatDuration } from '@/lib/format'

import { KIND_LABELS } from './describe'
import { ExportMenu } from './ExportMenu'
import { MediaPlayer } from './MediaPlayer'
import { Playback, PlaybackContext } from './playback'
import { ReportPanel } from './ReportPanel'
import { ScenesPanel } from './ScenesPanel'
import { ScoreCards } from './ScoreCards'
import { SystemsPanel } from './SystemsPanel'
import { SystemTimeline } from './SystemTimeline'
import { Transcript } from './Transcript'

export interface ResultsViewProps {
  analysis: Analysis
  result: AnalysisResult
  report: StoredReport | null | undefined
  source: MediaSource
  /** Buttons for the owner, next to Export. */
  actions?: React.ReactNode
  onRewrite?: () => void
  rewriting?: boolean
}

export function ResultsView({
  analysis,
  result,
  report,
  source,
  actions,
  onRewrite,
  rewriting,
}: ResultsViewProps) {
  const playback = useMemo(() => new Playback(result.duration_s), [result.duration_s])
  const { meta, state } = analysis
  const isVideo = meta.kind === 'video'

  return (
    <PlaybackContext.Provider value={playback}>
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-4 py-8 sm:px-6">
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex min-w-0 flex-col gap-1">
            <p className="text-xs text-muted-foreground">
              {KIND_LABELS[meta.kind]} · {formatDuration(result.duration_s)} ·{' '}
              {formatDateTime(meta.created_at)}
            </p>
            <h1 className="truncate text-2xl font-semibold tracking-tight">{meta.name}</h1>
            {state.reused_from ? (
              <p className="text-xs text-muted-foreground">
                The same file was analyzed before, so its brain response was reused.
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2 print:hidden">
            {actions}
            <ExportMenu data={{ analysis, result, report, source }} />
          </div>
        </header>

        <ScoreCards result={result} />

        <div className="grid items-start gap-8 lg:grid-cols-2">
          <section aria-labelledby="clip-title" className="flex flex-col gap-3">
            <h2 id="clip-title" className="text-sm font-medium">
              {isVideo
                ? 'The video'
                : meta.kind === 'text'
                  ? 'The script, read aloud'
                  : 'The audio'}
            </h2>
            <MediaPlayer source={source} kind={meta.kind} result={result} />
          </section>
          <BrainPanel result={result} source={source} />
        </div>

        <SystemTimeline
          result={result}
          source={source}
          showStrip={isVideo && Boolean(result.strip)}
        />

        <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <ReportPanel
            analysis={analysis}
            report={report}
            onRewrite={onRewrite}
            rewriting={rewriting}
          />
          <SystemsPanel systems={result.systems} hasBaseline={result.baseline != null} />
        </div>

        {isVideo && result.scenes.length > 1 ? (
          <ScenesPanel result={result} source={source} />
        ) : null}

        <Transcript words={result.transcript} language={result.language} />
      </div>
    </PlaybackContext.Provider>
  )
}
