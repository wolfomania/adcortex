// Words for the numbers of an analysis, shared by the results page and the
// exported report, so both say the same thing.
import type { AnalysisResult, LanguageInfo, MediaKind } from '@/api/types'
import { formatZ } from '@/lib/format'

export const KIND_LABELS: Record<MediaKind, string> = {
  video: 'Video',
  audio: 'Audio',
  text: 'Script',
}

export interface ScoreCard {
  label: string
  value: string
  unit?: string
  hint: string
}

/** The four headline numbers, each with what it measures. */
export function scoreCards(result: AnalysisResult): ScoreCard[] {
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

/** Which reference library the scores come from, or why there are none. */
export function referenceNote(result: AnalysisResult): string {
  const { baseline } = result
  return baseline
    ? `Reference library ${baseline.version}: ${baseline.description}`
    : 'No reference library is installed, so the scores and percentiles are unavailable.'
}

/**
 * What the z-scores compare against. Without a reference library the
 * backend compares each vertex and system with the clip's own average.
 */
export function zReference(result: AnalysisResult): string {
  return result.baseline ? 'the reference library' : "this clip's own average"
}

/** The spoken language, and a caveat when TRIBE v2 handles it less well. */
export function languageNote(language: LanguageInfo): string | null {
  const code = language.detected ?? language.requested
  if (!code || code === 'auto') {
    return null
  }
  const name = new Intl.DisplayNames(['en'], { type: 'language' }).of(code) ?? code
  const how = language.detected ? 'detected' : 'as requested'
  return language.full_support === false
    ? `${name} (${how}). TRIBE v2 was trained on English speech, so text responses are less reliable.`
    : `${name} (${how}).`
}

/** The systems that respond most during a scene, as "Faces +2.3 SD · …". */
export function sceneHighlights(result: AnalysisResult, sceneIndex: number, count = 2): string {
  const labels = new Map(result.systems.map((system) => [system.id, system.label]))
  const stats = result.scene_stats.find((stat) => stat.scene_index === sceneIndex)
  const top = Object.entries(stats?.mean_z ?? {})
    .filter((entry): entry is [string, number] => typeof entry[1] === 'number')
    .sort((a, b) => b[1] - a[1])
    .slice(0, count)
  return top.map(([id, z]) => `${labels.get(id) ?? id} ${formatZ(z)}`).join(' · ') || '–'
}
