// Saving the standalone HTML report: gathers the scene keyframes and pictures
// of the cortex, renders the document, and downloads it.
import { mediaUrls } from '@/api/endpoints'
import type { Analysis, AnalysisResult, MediaSource, Moment, StoredReport } from '@/api/types'
import { captureBrain } from '@/features/brain/snapshot'
import type { Playback } from '@/features/results/playback'
import { downloadFile, slugify } from '@/lib/download'
import { formatClock, formatZ } from '@/lib/format'

import { renderReportHtml, type BrainPicture } from './reportHtml'

/** Pictures of the cortex in a report, at most. */
const MAX_PICTURES = 4
/** Seconds between two pictures, at least: neighbouring frames look alike. */
const MIN_GAP_S = 2

export interface ReportSource {
  analysis: Analysis
  result: AnalysisResult
  report: StoredReport | null | undefined
  source: MediaSource
}

export interface PictureMoment {
  /** Seconds into the clip. */
  t: number
  /** The peaks in that second, strongest first. */
  peaks: Moment[]
}

/**
 * When to picture the cortex: the seconds with the strongest peaks, at least
 * `MIN_GAP_S` apart, in time order. Peaks in the same second share a picture.
 */
export function pictureMoments(moments: readonly Moment[]): PictureMoment[] {
  const peaks = moments.filter((moment) => moment.kind === 'peak').sort((a, b) => b.z - a.z)
  const times = peaks.reduce<number[]>((chosen, peak) => {
    const fits =
      chosen.length < MAX_PICTURES && chosen.every((t) => Math.abs(t - peak.t) >= MIN_GAP_S)
    return fits ? [...chosen, peak.t] : chosen
  }, [])
  return times
    .sort((a, b) => a - b)
    .map((t) => ({ t, peaks: peaks.filter((peak) => peak.t === t) }))
}

/** A file as a data URL, or null when it cannot be fetched: the report then leaves it out. */
async function fetchDataUrl(url: string): Promise<string | null> {
  const response = await fetch(url).catch(() => null)
  if (!response?.ok) {
    return null
  }
  const blob = await response.blob()
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result : null)
    reader.onerror = () => resolve(null)
    reader.readAsDataURL(blob)
  })
}

async function fetchKeyframes(
  result: AnalysisResult,
  source: MediaSource,
): Promise<Map<number, string>> {
  const scenes = result.scenes.filter((scene) => scene.keyframe)
  const urls = await Promise.all(
    scenes.map((scene) => fetchDataUrl(mediaUrls.keyframe(source, scene.index))),
  )
  const entries = scenes.flatMap((scene, i) => {
    const url = urls[i]
    return url ? [[scene.index, url] as const] : []
  })
  return new Map(entries)
}

async function brainPictures(result: AnalysisResult, playback: Playback): Promise<BrainPicture[]> {
  const labels = new Map(result.systems.map((system) => [system.id, system.label]))
  const moments = pictureMoments(result.moments)
  // Frame k covers second [k, k + 1); its middle shows it unblended.
  const times = moments.map((moment) => Math.min(moment.t + 0.5, result.duration_s))
  const images = await captureBrain(playback, times)
  return images.flatMap((image, i) => {
    const moment = moments[i]
    if (!moment) {
      return []
    }
    const peaks = moment.peaks.map(
      (peak) => `${labels.get(peak.system_id) ?? peak.system_id} ${formatZ(peak.z)}`,
    )
    return [{ t: moment.t, caption: [formatClock(moment.t), ...peaks].join(' · '), image }]
  })
}

/** Builds the standalone report and saves it as `<name>-<id>.html`. */
export async function exportReportHtml(data: ReportSource, playback: Playback): Promise<void> {
  // One after the other: the pictures move the playhead, which the page shows.
  const pictures = await brainPictures(data.result, playback)
  const keyframes = await fetchKeyframes(data.result, data.source)
  const html = renderReportHtml({
    analysis: data.analysis,
    result: data.result,
    report: data.report ?? null,
    keyframes,
    pictures,
    exportedAt: new Date(),
  })
  const { meta } = data.analysis
  downloadFile(`${slugify(meta.name)}-${meta.id}.html`, html, 'text/html')
}
