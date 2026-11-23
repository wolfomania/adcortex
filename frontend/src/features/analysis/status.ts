import type { Analysis, Status } from '@/api/types'

export const POLL_INTERVAL_MS = 1500

export function isTerminal(status: Status | undefined): boolean {
  return status === 'completed' || status === 'failed'
}

export interface StatusStep {
  status: Status
  label: string
  detail: string
}

/** The pipeline stages, in order, as the processing view explains them. */
export const STATUS_STEPS: readonly StatusStep[] = [
  {
    status: 'queued',
    label: 'Queued',
    detail: 'Waiting for a free worker. One analysis runs on the GPU at a time.',
  },
  {
    status: 'preparing',
    label: 'Preparing media',
    detail: 'Probing the file, making a browser preview, and finding scene cuts.',
  },
  {
    status: 'waiting_for_gpu',
    label: 'Starting the GPU',
    detail: 'Loading the brain model onto a GPU. The first run after a pause takes longer.',
  },
  {
    status: 'predicting',
    label: 'Predicting the brain response',
    detail: 'TRIBE v2 predicts the response of 20,484 points on the cortex, second by second.',
  },
  {
    status: 'analyzing',
    label: 'Measuring brain systems',
    detail: 'Grouping the cortex into 10 systems and comparing each with the reference set.',
  },
  {
    status: 'interpreting',
    label: 'Writing the report',
    detail: 'A language model reads the metrics, transcript, and media and writes the report.',
  },
]

const ORDER: Record<Status, number> = {
  queued: 0,
  preparing: 1,
  waiting_for_gpu: 2,
  predicting: 3,
  analyzing: 4,
  interpreting: 5,
  completed: 6,
  failed: -1,
}

export type StepState = 'done' | 'current' | 'upcoming'

/** Whether a stage is finished, running, or still ahead of `current`. */
export function stepState(step: Status, current: Status): StepState {
  const position = ORDER[current]
  const index = ORDER[step]
  if (position > index) {
    return 'done'
  }
  return position === index ? 'current' : 'upcoming'
}

export const STATUS_LABELS: Record<Status, string> = {
  queued: 'Queued',
  preparing: 'Preparing',
  waiting_for_gpu: 'Starting GPU',
  predicting: 'Predicting',
  analyzing: 'Analyzing',
  interpreting: 'Writing report',
  completed: 'Completed',
  failed: 'Failed',
}

/** Overall progress (0-1): live progress when present, else the stage position. */
export function progressFraction(analysis: Analysis): number {
  const status = analysis.state.status
  if (status === 'completed') {
    return 1
  }
  const live = analysis.progress?.fraction
  if (typeof live === 'number') {
    return Math.min(1, Math.max(0, live))
  }
  const index = ORDER[status]
  return index < 0 ? 0 : index / STATUS_STEPS.length
}

/** The message to show under the progress bar. */
export function progressMessage(analysis: Analysis): string {
  const live = analysis.progress?.message?.trim()
  if (live) {
    return live
  }
  const stored = analysis.state.message?.trim()
  if (stored) {
    return stored
  }
  return STATUS_STEPS.find((step) => step.status === analysis.state.status)?.detail ?? ''
}
