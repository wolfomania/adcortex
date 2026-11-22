import { readFile } from 'node:fs/promises'
import { pathToFileURL } from 'node:url'

import { expect, test, type Page } from '@playwright/test'

const NAME = 'Lumen launch: 30s master'

async function download(page: Page, item: string) {
  await page.getByRole('button', { name: 'Export' }).click()
  const [file] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('menuitem', { name: item }).click(),
  ])
  return file
}

test('exports the data, and a report that opens offline', async ({ page, context }, testInfo) => {
  await page.goto('/history')
  await page.getByRole('link', { name: NAME, exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: NAME })).toBeVisible()

  const json = await download(page, 'Download the data (JSON)')
  expect(json.suggestedFilename()).toMatch(/^lumen-launch-30s-master-.+\.json$/)
  const data = JSON.parse(await readFile(await json.path(), 'utf8')) as {
    analysis: { meta: { name: string } }
  }
  expect(data.analysis.meta.name).toBe(NAME)

  const html = await download(page, 'Download the report (HTML)')
  expect(html.suggestedFilename()).toMatch(/^lumen-launch-30s-master-.+\.html$/)
  const saved = testInfo.outputPath('report.html')
  await html.saveAs(saved)

  // Open the saved file with the network watched: it must not ask for anything.
  const report = await context.newPage()
  const requests: string[] = []
  report.on('request', (request) => {
    if (/^https?:/.test(request.url())) {
      requests.push(request.url())
    }
  })
  await report.goto(pathToFileURL(saved).href)
  await expect(report.getByRole('heading', { level: 1, name: NAME })).toBeVisible()
  await expect(report.getByRole('heading', { name: 'Brain systems over time' })).toBeVisible()
  await expect(report.getByRole('heading', { name: 'Scenes' })).toBeVisible()
  expect(requests).toEqual([])
})
