// The state of a mock A/B comparison at a given time.
import type { AnalysisResult, ComparisonState } from '@/api/types'

import type { ClipId } from './fixtures/clips'
import { templateComparison } from './fixtures/comparisons'
import { LUMEN_COMPARISON } from './fixtures/reports'
import { MOCK_MODEL } from './records'
import type { ComparisonJob } from './state'

/** How long the report model takes to compare two analyses. */
export const COMPARE_MS = 6000

export const COMPARISON_FAILURE =
  'The report model returned an invalid comparison twice. Try again in a few minutes.'

export interface ComparisonSide {
  id: string
  clipId: ClipId
  result: AnalysisResult
}

export interface ComparisonInput {
  job: ComparisonJob | undefined
  /** Time since the job started, scaled by the scenario speed. */
  elapsedMs: number
  nowIso: string
  a: ComparisonSide
  b: ComparisonSide
}

export function comparisonOf({ job, elapsedMs, nowIso, a, b }: ComparisonInput): ComparisonState {
  if (!job) {
    return { status: 'none', comparison: null, error: null }
  }
  if (elapsedMs < COMPARE_MS) {
    return { status: 'running', comparison: null, error: null }
  }
  if (job.fail) {
    return { status: 'failed', comparison: null, error: COMPARISON_FAILURE }
  }
  const handwritten = a.clipId === 'lumen-30s' && b.clipId === 'lumen-15s'
  return {
    status: 'completed',
    error: null,
    comparison: {
      a_id: a.id,
      b_id: b.id,
      model: MOCK_MODEL,
      created_at: nowIso,
      report: handwritten ? LUMEN_COMPARISON : templateComparison(a, b),
    },
  }
}
