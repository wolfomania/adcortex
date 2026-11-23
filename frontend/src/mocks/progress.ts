// How a mock analysis moves through the pipeline over time.
import type { MediaKind, Status } from '@/api/types'

export interface Stage {
  status: Status
  /** Duration at real-time speed. */
  ms: number
  /** Overall progress at the start and end of the stage (0-1). */
  from: number
  to: number
  message: (fraction: number) => string
}

export interface StageOptions {
  kind: MediaKind
  durationS: number
  /** The GPU worker has to start first. */
  coldGpu: boolean
  /** A report model writes a report at the end. */
  llm: boolean
  model: string
}

const PREPARING: Record<MediaKind, string> = {
  video: 'Probing the video, making a browser preview, and finding scene cuts',
  audio: 'Probing the audio and measuring loudness',
  text: 'Reading the script aloud with text-to-speech',
}

export function buildStages(options: StageOptions): Stage[] {
  const seconds = Math.ceil(options.durationS)
  const stages: Stage[] = [
    { status: 'queued', ms: 1200, from: 0, to: 0.03, message: () => 'Waiting for a free worker' },
    { status: 'preparing', ms: 2600, from: 0.03, to: 0.12, message: () => PREPARING[options.kind] },
  ]
  if (options.coldGpu) {
    stages.push({
      status: 'waiting_for_gpu',
      ms: 4200,
      from: 0.12,
      to: 0.22,
      message: () => 'Starting a GPU worker and loading TRIBE v2',
    })
  }
  stages.push(
    {
      status: 'predicting',
      ms: 7500,
      from: 0.22,
      to: 0.8,
      message: (f) =>
        `Predicting the cortical response: ${Math.min(seconds, Math.floor(f * seconds))} of ${seconds} s`,
    },
    {
      status: 'analyzing',
      ms: 1800,
      from: 0.8,
      to: 0.86,
      message: () => 'Measuring 10 brain systems against the reference set',
    },
  )
  if (options.llm) {
    stages.push({
      status: 'interpreting',
      ms: 5000,
      from: 0.86,
      to: 0.99,
      message: () => `Writing the report with ${options.model}`,
    })
  }
  return stages
}

export interface Phase {
  status: Status
  /** Overall progress (0-1). */
  fraction: number
  message: string
}

/**
 * Where a job is after `elapsedMs` (already scaled by the scenario speed).
 * With `failAt`, the job fails halfway through that stage.
 */
export function phaseAt(stages: readonly Stage[], elapsedMs: number, failAt?: Status): Phase {
  let start = 0
  for (const stage of stages) {
    const end = start + stage.ms
    if (stage.status === failAt && elapsedMs >= start + stage.ms / 2) {
      return { status: 'failed', fraction: stage.from, message: '' }
    }
    if (elapsedMs < end) {
      const within = Math.max(0, (elapsedMs - start) / stage.ms)
      return {
        status: stage.status,
        fraction: stage.from + within * (stage.to - stage.from),
        message: stage.message(within),
      }
    }
    start = end
  }
  return { status: 'completed', fraction: 1, message: '' }
}

/** Real-time length of all stages. */
export function totalMs(stages: readonly Stage[]): number {
  return stages.reduce((sum, stage) => sum + stage.ms, 0)
}
