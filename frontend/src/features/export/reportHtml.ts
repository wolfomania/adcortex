// The standalone report: one HTML file with the scores, the written report,
// pictures of the cortex, the timeline, and the scene keyframes. Everything
// is inline (styles, images, data), so it opens offline and prints well.
import type { Analysis, AnalysisResult, StoredReport } from '@/api/types'
import {
  KIND_LABELS,
  languageNote,
  referenceNote,
  sceneHighlights,
  scoreCards,
  zReference,
} from '@/features/results/describe'
import { heatFill, timeTicks } from '@/features/results/timeline'
import { CONFIDENCE_LABELS } from '@/features/systems/catalog'
import {
  formatClock,
  formatDateTime,
  formatDuration,
  formatPercentile,
  formatZ,
} from '@/lib/format'

export interface BrainPicture {
  /** Seconds into the clip. */
  t: number
  caption: string
  /** A PNG data URL. */
  image: string
}

export interface ReportHtmlInput {
  analysis: Analysis
  result: AnalysisResult
  report: StoredReport | null
  /** Scene keyframes as data URLs, by scene index. */
  keyframes: ReadonlyMap<number, string>
  pictures: readonly BrainPicture[]
  exportedAt: Date
}

const ENTITIES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

/** Text made safe for HTML content and quoted attributes. */
export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (char) => ENTITIES[char] ?? char)
}

const e = escapeHtml

/** Only inline images: the file must not reach the network. */
function imageSource(url: string): string | null {
  return /^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(url) ? url : null
}

function section(title: string, body: string): string {
  return `<section><h2>${e(title)}</h2>${body}</section>`
}

function header({ analysis, result, exportedAt }: ReportHtmlInput): string {
  const { meta } = analysis
  return `<header>
<p class="note">${e(KIND_LABELS[meta.kind])} · ${e(formatDuration(result.duration_s))} · ${e(formatDateTime(meta.created_at))}</p>
<h1>${e(meta.name)}</h1>
<p class="note">Exported from Neuro-Marketing Validator on ${e(formatDateTime(exportedAt))}.</p>
</header>`
}

function scores(result: AnalysisResult): string {
  const cards = scoreCards(result)
    .map(
      (card) =>
        `<div class="card"><dt>${e(card.label)}</dt><dd><span class="value">${e(card.value)}</span>${
          card.unit ? `<span class="unit">${e(card.unit)}</span>` : ''
        }</dd><p>${e(card.hint)}</p></div>`,
    )
    .join('')
  return section(
    'Scores',
    `<dl class="cards">${cards}</dl><p class="note">${e(referenceNote(result))}</p>`,
  )
}

function timedList(items: readonly { t?: number | null; body: string }[]): string {
  const rows = items.map(
    (item) =>
      `<li><span class="time">${item.t == null ? '' : e(formatClock(item.t))}</span><div>${item.body}</div></li>`,
  )
  return `<ol class="timed">${rows.join('')}</ol>`
}

function writtenReport(stored: StoredReport | null): string {
  if (!stored) {
    return section('Report', '<p class="note">This analysis has no written report.</p>')
  }
  const { report } = stored
  const list = (items: readonly string[]) =>
    `<ul>${items.map((item) => `<li>${e(item)}</li>`).join('')}</ul>`
  const moments = timedList(
    report.key_moments.map((moment) => ({
      t: moment.t,
      body: `<p class="strong">${e(moment.title)}</p><p>${e(moment.what_happens)}</p><p>${e(moment.brain_response)}</p><p class="note">${e(moment.why_it_matters)}</p>`,
    })),
  )
  const recommendations = timedList(
    report.recommendations.map((item) => ({
      t: item.t,
      body: `<p class="strong">${e(item.title)}</p><p>${e(item.detail)}</p>`,
    })),
  )
  return section(
    'Report',
    `<p class="headline">${e(report.headline)}</p>
<p>${e(report.summary)}</p>
<div class="columns"><div><h3>Strengths</h3>${list(report.strengths)}</div><div><h3>Risks</h3>${list(report.risks)}</div></div>
${report.key_moments.length ? `<h3>Key moments</h3>${moments}` : ''}
${report.recommendations.length ? `<h3>Recommendations</h3>${recommendations}` : ''}
<p class="note">Written by ${e(stored.model)} from the metrics above.</p>`,
  )
}

function cortex(result: AnalysisResult, pictures: readonly BrainPicture[]): string {
  const figures = pictures.flatMap((picture) => {
    const src = imageSource(picture.image)
    if (!src) {
      return []
    }
    const alt = `Predicted cortical response at ${formatClock(picture.t)}`
    return [
      `<figure><img src="${src}" alt="${e(alt)}"><figcaption>${e(picture.caption)}</figcaption></figure>`,
    ]
  })
  if (!figures.length) {
    return ''
  }
  return section(
    'The cortex at the peaks',
    `<div class="pictures">${figures.join('')}</div>
<p class="note">TRIBE v2's predicted response, as the app's 3D view drew it: red is above ${e(zReference(result))}, blue below.</p>`,
  )
}

const LABEL_WIDTH = 132
const PLOT_WIDTH = 628
const ROW_HEIGHT = 16
const ROW_GAP = 3
const AXIS_HEIGHT = 18

function timeline(result: AnalysisResult): string {
  const { systems, duration_s: duration } = result
  const columns = Math.max(1, ...systems.map((system) => system.values.length))
  const cell = PLOT_WIDTH / columns
  const pitch = ROW_HEIGHT + ROW_GAP
  const rows = systems.map((system, row) => {
    const y = row * pitch
    const cells = system.values.map((z, k) => {
      const value = z === null ? 'not applicable' : formatZ(z)
      return `<rect x="${(LABEL_WIDTH + k * cell).toFixed(2)}" y="${y}" width="${(cell + 0.4).toFixed(2)}" height="${ROW_HEIGHT}" style="fill:${heatFill(z)}"><title>${e(`${system.label} at ${formatClock(k)}: ${value}`)}</title></rect>`
    })
    return `<text x="0" y="${y + ROW_HEIGHT - 4}">${e(system.label)}</text>${cells.join('')}`
  })
  const axis = systems.length * pitch + AXIS_HEIGHT - 6
  const ticks = timeTicks(duration, 8).map((t) => {
    const x = LABEL_WIDTH + (t / duration) * PLOT_WIDTH
    const anchor = t === 0 ? 'start' : t >= duration ? 'end' : 'middle'
    return `<text class="tick" x="${x.toFixed(2)}" y="${axis}" text-anchor="${anchor}">${e(formatClock(t))}</text>`
  })
  const height = systems.length * pitch + AXIS_HEIGHT
  return section(
    'Brain systems over time',
    `<svg viewBox="0 0 ${LABEL_WIDTH + PLOT_WIDTH} ${height}" role="img" aria-label="Heatmap of the brain systems over time">${rows.join('')}${ticks.join('')}</svg>
<p class="note">z-scores against ${e(zReference(result))}, one column per second: red is above, blue below.</p>`,
  )
}

function systemsTable(result: AnalysisResult): string {
  const rows = result.systems.map((system) => {
    const applicable = system.applicable !== false
    return `<tr${applicable ? '' : ' class="note"'}><th scope="row">${e(system.label)}</th><td class="num">${
      applicable ? e(formatZ(system.mean_z)) : 'needs a picture'
    }</td><td class="num">${e(formatPercentile(system.percentile))}</td><td class="num">${e(
      formatPercentile(system.library_percentile),
    )}</td><td>${e(CONFIDENCE_LABELS[system.confidence])}</td></tr>`
  })
  return section(
    'Brain systems',
    `<table><thead><tr><th scope="col">System</th><th scope="col" class="num">Mean</th><th scope="col" class="num">vs reference</th><th scope="col" class="num">vs your library</th><th scope="col">Confidence</th></tr></thead><tbody>${rows.join('')}</tbody></table>`,
  )
}

function scenes(result: AnalysisResult, keyframes: ReadonlyMap<number, string>): string {
  const items = result.scenes.flatMap((scene) => {
    const src = imageSource(keyframes.get(scene.index) ?? '')
    if (!src) {
      return []
    }
    return [
      `<li><img src="${src}" alt="${e(`Scene ${scene.index + 1}`)}"><span class="time">${e(
        `${formatClock(scene.start)}–${formatClock(scene.end)}`,
      )}</span><span>${e(sceneHighlights(result, scene.index))}</span></li>`,
    ]
  })
  return items.length ? section('Scenes', `<ol class="scenes">${items.join('')}</ol>`) : ''
}

function transcript(result: AnalysisResult): string {
  if (!result.transcript.length) {
    return ''
  }
  const note = languageNote(result.language)
  const text = result.transcript.map((word) => word.text).join(' ')
  return section('Transcript', `${note ? `<p class="note">${e(note)}</p>` : ''}<p>${e(text)}</p>`)
}

/** The analysis as JSON, inert: `<` is escaped, so the text cannot close the element. */
function embeddedData({ analysis, result, report }: ReportHtmlInput): string {
  const json = JSON.stringify({ analysis, result, report }).replace(/</g, '\\u003c')
  return `<script type="application/json" id="analysis-data">${json}</script>`
}

const STYLES = `
:root {
  color-scheme: light;
  --fg: #0b0b0b;
  --muted: #5b5a56;
  --border: rgb(11 11 11 / 0.12);
  --card: #fafaf8;
  --viz-neg: oklch(0.5 0.15 255);
  --viz-pos: oklch(0.53 0.17 27);
  --viz-mid: oklch(0.94 0 0);
  --surface-sunken: #f2f2ef;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  color: var(--fg);
  background: #fff;
  line-height: 1.5;
}
* { box-sizing: border-box; }
body { margin: 0; }
main { max-width: 880px; margin: 0 auto; padding: 40px 24px 64px; }
h1 { font-size: 28px; line-height: 1.2; letter-spacing: -0.01em; margin: 4px 0 6px; }
h2 { font-size: 16px; margin: 0 0 12px; }
h3 { font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); margin: 20px 0 8px; }
section { margin-top: 36px; }
p { margin: 0 0 6px; }
.note { font-size: 12px; color: var(--muted); }
.strong { font-weight: 600; }
.headline { font-size: 19px; font-weight: 600; line-height: 1.35; }
.cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 0 0 8px; }
.card { border: 1px solid var(--border); border-radius: 8px; padding: 12px; background: var(--card); }
.card dt { font-size: 12px; color: var(--muted); }
.card dd { margin: 4px 0 6px; }
.card p { font-size: 12px; color: var(--muted); margin: 0; }
.value { font: 600 28px/1 var(--mono); }
.unit { font-size: 13px; color: var(--muted); margin-left: 4px; }
.columns { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
ul { margin: 0; padding-left: 18px; }
li { margin-bottom: 4px; }
.timed { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }
.timed li { display: grid; grid-template-columns: 48px 1fr; gap: 12px; margin: 0; }
.time { font: 12px/1.6 var(--mono); color: var(--muted); }
.pictures { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
figure { margin: 0; }
figure img { display: block; width: 100%; height: auto; border: 1px solid var(--border); border-radius: 8px; }
figcaption { font-size: 12px; color: var(--muted); margin-top: 4px; }
svg { display: block; width: 100%; height: auto; font: 11px ui-sans-serif, system-ui, sans-serif; }
svg text { fill: var(--fg); }
svg .tick { fill: var(--muted); font: 10px var(--mono); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); }
thead th { font-size: 12px; font-weight: 500; color: var(--muted); }
.num { text-align: right; font-family: var(--mono); font-variant-numeric: tabular-nums; }
.scenes { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.scenes li { display: flex; flex-direction: column; gap: 4px; font-size: 12px; margin: 0; }
.scenes img { display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: cover; border-radius: 6px; }
footer { margin-top: 48px; padding-top: 16px; border-top: 1px solid var(--border); font-size: 12px; color: var(--muted); }
@media (max-width: 640px) {
  .cards, .scenes { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .columns, .pictures { grid-template-columns: 1fr; }
}
@media print {
  main { padding: 0; }
  .card, figure, .timed li, .scenes li, tr { break-inside: avoid; }
}
`

/** The whole report as one HTML document. */
export function renderReportHtml(input: ReportHtmlInput): string {
  const { analysis, result } = input
  const body = [
    header(input),
    scores(result),
    writtenReport(input.report),
    cortex(result, input.pictures),
    timeline(result),
    systemsTable(result),
    scenes(result, input.keyframes),
    transcript(result),
  ].join('\n')
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'">
<title>${e(analysis.meta.name)} · Neuro-Marketing Validator</title>
<style>${STYLES}</style>
</head>
<body>
<main>
${body}
<footer>
<p>TRIBE v2 predicts how an average viewer's cortex responds to the clip, second by second. It does not forecast sales or individual reactions; treat the findings as hypotheses to test.</p>
<p>The data behind this report is embedded in this file as JSON (the element with id "analysis-data").</p>
</footer>
</main>
${embeddedData(input)}
</body>
</html>
`
}
