import { expect, test, type Page } from '@playwright/test'

test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })

async function expectNoSideScroll(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
}

test('fits every page on a phone', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('form', { name: 'New analysis' })).toBeVisible()
  await expectNoSideScroll(page)

  await page.goto('/history')
  await expect(page.getByRole('heading', { level: 1, name: 'History' })).toBeVisible()
  await expectNoSideScroll(page)

  await page.getByRole('link', { name: 'Lumen launch: 30s master', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Brain systems over time' })).toBeVisible()
  await expectNoSideScroll(page)

  await page.goto('/history')
  await page.getByRole('checkbox', { name: 'Select “Lumen launch: 30s master” to compare' }).check()
  await page
    .getByRole('checkbox', { name: 'Select “Lumen launch: 15s cut-down” to compare' })
    .check()
  await page.getByRole('button', { name: /^Compare/ }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Comparison' })).toBeVisible()
  await expectNoSideScroll(page)
})
