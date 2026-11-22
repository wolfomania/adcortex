import { describe, expect, it } from 'vitest'

import { mockDb } from '@/test/server'

import { escapeHtml, renderReportHtml, type ReportHtmlInput } from './reportHtml'

const PNG = 'data:image/png;base64,iVBORw0KGgo='
const JPEG = 'data:image/jpeg;base64,/9j/4AAQSkZJRg=='

function input(overrides: Partial<ReportHtmlInput> = {}): ReportHtmlInput {
  const record = mockDb()
    .state()
    .records.find((item) => item.name === 'Lumen launch: 30s master')
  const detail = record && mockDb().detail(record.id)
  if (!detail?.result) {
    throw new Error('Missing the seeded analysis')
  }
  return {
    analysis: detail.analysis,
    result: detail.result,
    report: detail.report ?? null,
    keyframes: new Map([[0, JPEG]]),
    pictures: [{ t: 3, caption: '0:03 · Faces +2.4 SD', image: PNG }],
    exportedAt: new Date('2026-11-22T12:00:00Z'),
    ...overrides,
  }
}

function parse(html: string): Document {
  return new DOMParser().parseFromString(html, 'text/html')
}

describe('renderReportHtml', () => {
  it('writes every section of the report', () => {
    const doc = parse(renderReportHtml(input()))

    expect(doc.querySelector('h1')?.textContent).toBe('Lumen launch: 30s master')
    expect([...doc.querySelectorAll('h2')].map((heading) => heading.textContent)).toEqual([
      'Scores',
      'Report',
      'The cortex at the peaks',
      'Brain systems over time',
      'Brain systems',
      'Scenes',
      'Transcript',
    ])
    expect(doc.querySelector('figcaption')?.textContent).toBe('0:03 · Faces +2.4 SD')
    expect(doc.querySelector('.headline')?.textContent).toBeTruthy()
  })

  it('draws one heatmap cell per system and second', () => {
    const { result } = input()
    const doc = parse(renderReportHtml(input()))

    const cells = result.systems.reduce((sum, system) => sum + system.values.length, 0)
    expect(doc.querySelectorAll('svg rect')).toHaveLength(cells)
    expect(doc.querySelectorAll('tbody tr')).toHaveLength(result.systems.length)
  })

  it('loads nothing from the network', () => {
    const html = renderReportHtml(input())
    const doc = parse(html)

    const csp = doc.querySelector('meta[http-equiv="Content-Security-Policy"]')
    expect(csp?.getAttribute('content')).toBe(
      "default-src 'none'; img-src data:; style-src 'unsafe-inline'",
    )
    const sources = [...doc.querySelectorAll('[src], [href]')].map(
      (element) => element.getAttribute('src') ?? element.getAttribute('href'),
    )
    expect(sources.every((source) => source?.startsWith('data:image/'))).toBe(true)
    expect(html).not.toContain('url(')
    expect([...doc.querySelectorAll('script')].map((script) => script.type)).toEqual([
      'application/json',
    ])
  })

  it('leaves out pictures that are not inline images', () => {
    const doc = parse(
      renderReportHtml(
        input({
          keyframes: new Map([[0, 'javascript:alert(1)']]),
          pictures: [{ t: 3, caption: 'remote', image: 'https://example.com/brain.png' }],
        }),
      ),
    )

    expect(doc.querySelectorAll('img')).toHaveLength(0)
    expect(doc.body.textContent).not.toContain('The cortex at the peaks')
    expect(doc.body.textContent).not.toContain('Scenes')
  })

  it('escapes text from the analysis, in the page and in the embedded data', () => {
    const name = '</script><img src=x onerror=alert(1)>'
    const base = input()
    const analysis = { ...base.analysis, meta: { ...base.analysis.meta, name } }
    const html = renderReportHtml({ ...base, analysis })
    const doc = parse(html)

    expect(doc.querySelector('h1')?.textContent).toBe(name)
    expect(doc.querySelectorAll('img[onerror]')).toHaveLength(0)
    expect(html.match(/<\/script>/g)).toHaveLength(1)
    const data = JSON.parse(doc.getElementById('analysis-data')?.textContent ?? '') as unknown
    expect(data).toEqual({ analysis, result: base.result, report: base.report })
  })

  it('says what the z-scores compare against', () => {
    const base = input()
    const withBaseline = parse(renderReportHtml(base)).body.textContent
    const withoutBaseline = parse(
      renderReportHtml({ ...base, result: { ...base.result, baseline: null } }),
    ).body.textContent

    expect(withBaseline).toContain('z-scores against the reference library')
    expect(withBaseline).toContain('Mean')
    expect(withoutBaseline).toContain("z-scores against this clip's own average")
    expect(withoutBaseline).toContain('No reference library is installed')
    expect(withoutBaseline).toContain('Strongest second')
  })

  it('says when there is no written report', () => {
    const doc = parse(renderReportHtml(input({ report: null })))

    expect(doc.body.textContent).toContain('This analysis has no written report.')
  })
})

describe('escapeHtml', () => {
  it('escapes the characters that HTML gives meaning to', () => {
    expect(escapeHtml(`<a href="x">'&'</a>`)).toBe(
      '&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;',
    )
  })
})
