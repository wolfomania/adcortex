import { fileURLToPath } from 'node:url'

import { expect, test } from '@playwright/test'

const VIDEO = fileURLToPath(new URL('../src/mocks/media/lumen-15s.mp4', import.meta.url))

test('uploads a video and follows it to the results', async ({ page }) => {
  // `instant` runs the mock pipeline a thousand times faster than real time.
  await page.goto('/?mock=instant')
  await page.locator('input[type=file]').setInputFiles(VIDEO)
  await page.getByRole('button', { name: 'Analyze' }).click()

  await expect(page.getByRole('heading', { level: 1, name: 'lumen-15s' })).toBeVisible()
  await expect(page.getByText('Response index')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Brain systems over time' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Brain systems', exact: true })).toBeVisible()
})

test('follows a script through the pipeline stages', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('tab', { name: 'Script' }).click()
  await page
    .getByRole('textbox', { name: 'Script' })
    .fill('Meet Lumen, the lamp that learns your evenings and dims itself when the film starts.')
  await page.getByRole('button', { name: 'Analyze' }).click()

  await expect(page.getByRole('list', { name: 'Stages' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 1, name: /^Meet Lumen/ })).toBeVisible()
})

test('explains an analysis that does not exist', async ({ page }) => {
  await page.goto('/a/20990101-000000-abcdef')

  await expect(page.getByRole('heading', { name: 'Analysis not found' })).toBeVisible()
})
