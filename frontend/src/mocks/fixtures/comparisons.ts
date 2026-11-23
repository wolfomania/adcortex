// A templated A/B comparison for pairs without a hand-written one.
import type { AnalysisResult, ComparisonReport, SystemSeries } from '@/api/types'

interface Side {
  result: AnalysisResult
}

const CLEAR_GAP = 5

/** Percentile when there is a baseline, otherwise a z-based stand-in. */
function level(series: SystemSeries): number {
  return series.percentile ?? 50 + 30 * series.mean_z
}

function describe(series: SystemSeries): string {
  if (series.percentile === null || series.percentile === undefined) {
    const sign = series.mean_z >= 0 ? '+' : ''
    return `${series.label}: ${sign}${series.mean_z.toFixed(2)} SD on average.`
  }
  return `${series.label}: ${Math.round(series.percentile)}th percentile.`
}

function strengths(own: AnalysisResult, other: AnalysisResult): string[] {
  const theirs = new Map(other.systems.map((s) => [s.id, s]))
  const ahead = own.systems
    .flatMap((s) => {
      const match = theirs.get(s.id)
      if (!match || s.applicable === false || match.applicable === false) {
        return []
      }
      return [{ s, gap: level(s) - level(match) }]
    })
    .filter(({ gap }) => gap > CLEAR_GAP)
    .sort((x, y) => y.gap - x.gap)
    .slice(0, 3)
    .map(({ s }) => describe(s))
  return ahead.length > 0 ? ahead : ['No system is clearly stronger than in the other version.']
}

export function templateComparison(a: Side, b: Side): ComparisonReport {
  const first = a.result.scores.response_index ?? 50
  const second = b.result.scores.response_index ?? 50
  const leader = first >= second ? 'A' : 'B'
  const gap = Math.abs(first - second)
  const close = gap < CLEAR_GAP
  return {
    headline: close
      ? 'The two versions draw a similar overall response; they differ in which systems lead.'
      : `Version ${leader} draws the stronger overall response, by ${Math.round(gap)} percentile points.`,
    a_strengths: strengths(a.result, b.result),
    b_strengths: strengths(b.result, a.result),
    recommendation: close
      ? "Keep the scenes behind each version's leading systems and test a combined cut."
      : `Build the next cut on version ${leader}, and borrow the scenes where the other version is ahead.`,
  }
}
