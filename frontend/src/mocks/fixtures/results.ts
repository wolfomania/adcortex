// Assemble an `AnalysisResult` for a mock clip.
import type {
  AnalysisResult,
  AnalysisSummary,
  BaselineRef,
  LanguageInfo,
  Scene,
  SystemSeries,
  Word,
} from '@/api/types'
import { N_VERTICES } from '@/features/brain/assets'
import { SYSTEM_CATALOG } from '@/features/systems/catalog'

import type { Clip, Sentence } from './clips'
import { round } from './math'
import { computeScores, findMoments, referencePercentile, sceneStats, topSystems } from './metrics'
import { isApplicable, secondsGrid, systemCurves, type CurveOptions } from './signals'

export const MOCK_BASELINE: BaselineRef = {
  description: '5 public-domain TV commercials from the Prelinger Archives, 60-85 s each.',
  n_clips: 5,
  version: 'v1',
}

/** Spread each sentence's words over its span in proportion to their length. */
export function spreadWords(sentences: readonly Sentence[]): Word[] {
  return sentences.flatMap((sentence) => {
    const tokens = sentence.text.split(/\s+/).filter(Boolean)
    const weights = tokens.map((token) => token.length + 1)
    const total = weights.reduce((a, b) => a + b, 0)
    const span = sentence.end - sentence.start
    let cursor = sentence.start
    return tokens.map((text, i) => {
      const start = cursor
      cursor += (span * weights[i]!) / total
      return { text, start: round(start, 2), end: round(cursor - 0.04, 2) }
    })
  })
}

function scenesOf(clip: Clip): Scene[] {
  return clip.scenes.map((scene, index) => ({
    index,
    start: scene.start,
    end: scene.end,
    keyframe: clip.kind === 'video' ? `keyframes/${String(index).padStart(3, '0')}.jpg` : null,
  }))
}

function seriesOf(clip: Clip, curves: Record<string, number[]>, baseline: boolean): SystemSeries[] {
  return SYSTEM_CATALOG.map((system) => {
    const values = curves[system.id] ?? []
    const meanZ = round(values.reduce((a, b) => a + b, 0) / Math.max(1, values.length), 3)
    const applicable = isApplicable(system.id, clip)
    return {
      id: system.id,
      label: system.label,
      confidence: system.confidence,
      applicable,
      values,
      mean_z: meanZ,
      percentile: baseline && applicable ? referencePercentile(meanZ) : null,
      library_percentile: null,
    }
  })
}

export interface ResultSpec extends CurveOptions {
  clip: Clip
  language: LanguageInfo
  /** Replaces the clip's own transcript (a dub, for example). */
  sentences?: readonly Sentence[]
}

export interface BuiltResult {
  result: AnalysisResult
  summary: AnalysisSummary
}

export function buildResult(spec: ResultSpec): BuiltResult {
  const { clip } = spec
  const curves = systemCurves(clip, spec)
  const series = seriesOf(clip, curves, spec.baseline)
  const applicable = series.filter((s) => s.applicable).map((s) => s.id)
  const labels = Object.fromEntries(series.map((s) => [s.id, s.label]))
  const moments = findMoments(
    Object.fromEntries(applicable.map((id) => [id, curves[id] ?? []])),
    labels,
  )
  const percentiles = Object.fromEntries(series.map((s) => [s.id, s.percentile ?? null]))
  const scores = computeScores(
    curves,
    applicable,
    percentiles,
    moments.filter((m) => m.kind === 'peak').length,
    spec.baseline,
  )
  const scenes = scenesOf(clip)
  const n = secondsGrid(clip.duration)
  const result: AnalysisResult = {
    version: 2,
    duration_s: clip.duration,
    times: Array.from({ length: n }, (_, k) => k),
    systems: series,
    scenes,
    scene_stats: sceneStats(scenes, curves, applicable),
    moments,
    scores,
    transcript: spreadWords(spec.sentences ?? clip.sentences),
    envelope: clip.envelope,
    envelope_hz: 10,
    frames: { file: 'frames.bin', n_frames: n, n_vertices: N_VERTICES, vmin: -3, vmax: 3 },
    baseline: spec.baseline ? MOCK_BASELINE : null,
    language: spec.language,
    strip: clip.stripUrl ? 'strip.jpg' : null,
    strip_columns: 10,
  }
  const summary: AnalysisSummary = {
    duration_s: clip.duration,
    response_index: scores.response_index,
    top_systems: topSystems(series),
    system_means: Object.fromEntries(series.map((s) => [s.id, round(0.012 * s.mean_z + 0.004, 5)])),
  }
  return { result, summary }
}
