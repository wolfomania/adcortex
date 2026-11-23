// A stored mock analysis and how it looks through the API at a given time.
// Records are plain JSON, so the mock backend can keep them across reloads.
import type {
  Analysis,
  AnalysisState,
  AnalysisSummary,
  LanguageInfo,
  MediaInfo,
  Progress,
  Status,
} from '@/api/types'

import { CLIPS, type Clip, type ClipId } from './fixtures/clips'
import type { FixtureSpec, LlmOutcome } from './fixtures/seeds'
import { buildStages, phaseAt, type Phase } from './progress'

export const MOCK_MODEL = 'google:gemini-4-hydrogen'

export interface JobSpec {
  /** Wall-clock time the job started (ms). */
  startedAt: number
  coldGpu: boolean
  llm: boolean
  /** The job fails halfway through this stage. */
  failAt: Status | null
  /** Only the report is being rewritten; metrics stay available. */
  reportOnly: boolean
}

export interface MockRecord {
  id: string
  name: string
  clipId: ClipId
  createdAt: number
  requestedLanguage: string
  language: LanguageInfo
  fixture: FixtureSpec
  /** Outcome of the report step once the job is done. */
  llm: { status: LlmOutcome; error?: string }
  /** Error shown once the analysis has failed. */
  failure: string | null
  reusedFrom: string | null
  sha256: string
  job: JobSpec | null
}

export function clipOf(record: MockRecord): Clip {
  return CLIPS[record.clipId]
}

/** Status, progress, and message of a record at wall-clock time `now`. */
export function phaseOf(record: MockRecord, now: number, speed: number): Phase {
  const { job } = record
  if (!job) {
    return record.failure
      ? { status: 'failed', fraction: 0, message: '' }
      : { status: 'completed', fraction: 1, message: '' }
  }
  const clip = clipOf(record)
  const stages = buildStages({
    kind: clip.kind,
    durationS: clip.duration,
    coldGpu: job.coldGpu,
    llm: job.llm,
    model: MOCK_MODEL,
  }).filter((stage) => !job.reportOnly || stage.status === 'interpreting')
  return phaseAt(stages, (now - job.startedAt) * speed, job.failAt ?? undefined)
}

/** Are the metrics available in this phase? */
export function hasMetrics(record: MockRecord, phase: Phase): boolean {
  return (
    phase.status === 'completed' || (record.job?.reportOnly === true && phase.status !== 'failed')
  )
}

function mediaInfo(clip: Clip): MediaInfo {
  const video = clip.kind === 'video'
  return {
    duration_s: clip.duration,
    format_name: 'mov,mp4,m4a,3gp,3g2,mj2',
    has_audio: true,
    has_video: video,
    width: video ? clip.width : null,
    height: video ? clip.height : null,
    fps: video ? 24 : null,
    video_codec: video ? 'h264' : null,
    audio_codec: 'aac',
  }
}

const ORDER: readonly Status[] = [
  'queued',
  'preparing',
  'waiting_for_gpu',
  'predicting',
  'analyzing',
  'interpreting',
  'completed',
]

/** The media was probed: preparing is over, or the job failed after it. */
function probed(record: MockRecord, phase: Phase): boolean {
  if (phase.status === 'failed') {
    return record.job?.failAt != null && record.job.failAt !== 'preparing'
  }
  return ORDER.indexOf(phase.status) > ORDER.indexOf('preparing')
}

function timings(record: MockRecord): Record<string, number> {
  const predict = record.reusedFrom ? 0 : Math.round(clipOf(record).duration * 13) / 10
  const base: Record<string, number> = { prepare: 3.1, predict, analyze: 0.9 }
  return record.llm.status === 'skipped' ? base : { ...base, report: 14.2 }
}

function stateOf(
  record: MockRecord,
  phase: Phase,
  summary: AnalysisSummary | null,
  nowIso: string,
): AnalysisState {
  const done = phase.status === 'completed'
  const failed = phase.status === 'failed'
  const { status, error } = record.llm
  return {
    status: phase.status,
    message: failed ? 'Failed' : done ? 'Completed' : phase.message,
    error: failed ? (record.failure ?? 'The analysis failed.') : null,
    media: probed(record, phase) ? mediaInfo(clipOf(record)) : null,
    language: hasMetrics(record, phase) ? record.language : null,
    llm: done
      ? {
          status,
          error: error ?? null,
          model: status === 'skipped' ? null : MOCK_MODEL,
          input_mode: status === 'ok' ? clipOf(record).kind : null,
        }
      : null,
    summary,
    reused_from: record.reusedFrom,
    timings: done ? timings(record) : {},
    updated_at: nowIso,
  }
}

export interface AnalysisView {
  phase: Phase
  summary: AnalysisSummary | null
  nowIso: string
  /** Include live progress (the status route); lists leave it out. */
  live: boolean
}

export function toAnalysis(record: MockRecord, view: AnalysisView): Analysis {
  const { phase, nowIso } = view
  const running = phase.status !== 'completed' && phase.status !== 'failed'
  const progress: Progress | null =
    view.live && running
      ? {
          status: phase.status,
          fraction: Math.round(phase.fraction * 1000) / 1000,
          message: phase.message,
          updated_at: nowIso,
        }
      : null
  const clip = clipOf(record)
  return {
    meta: {
      id: record.id,
      name: record.name,
      kind: clip.kind,
      language: record.requestedLanguage,
      created_at: new Date(record.createdAt).toISOString(),
      source: {
        filename: clip.filename,
        extension: clip.filename.slice(clip.filename.lastIndexOf('.')),
        size_bytes: clip.sizeBytes,
        sha256: record.sha256,
      },
    },
    progress,
    state: stateOf(record, phase, view.summary, nowIso),
  }
}

/** A sortable analysis id: `YYYYMMDD-HHMMSS-xxxxxx` (UTC), as the backend makes them. */
export function analysisId(createdAt: number, hash: number): string {
  const stamp = new Date(createdAt)
    .toISOString()
    .replace(/[-:]/g, '')
    .replace('T', '-')
    .slice(0, 15)
  return `${stamp}-${(hash >>> 0).toString(16).padStart(8, '0').slice(-6)}`
}
