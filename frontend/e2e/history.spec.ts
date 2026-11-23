import { expect, test } from '@playwright/test'

test('picks two analyses and compares them', async ({ page }) => {
  await page.goto('/history')
  await page.getByRole('checkbox', { name: 'Select “Lumen launch: 30s master” to compare' }).check()
  await page
    .getByRole('checkbox', { name: 'Select “Lumen launch: 15s cut-down” to compare' })
    .check()
  await page.getByRole('button', { name: /^Compare/ }).click()

  await expect(page.getByRole('heading', { level: 1, name: 'Comparison' })).toBeVisible()
  const scores = page.getByRole('table', { name: 'Scores' })
  await expect(scores.getByRole('rowheader', { name: 'Hook' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Brain systems' })).toBeVisible()
})

test('renames and deletes an analysis', async ({ page }) => {
  await page.goto('/history')
  await page.getByRole('button', { name: 'Actions for “Holiday teaser”' }).click()
  await page.getByRole('menuitem', { name: 'Rename' }).click()
  const name = page.getByRole('textbox', { name: 'Name' })
  await name.fill('Holiday teaser, final')
  await name.press('Enter')
  await expect(page.getByRole('link', { name: 'Holiday teaser, final' })).toBeVisible()

  await page.getByRole('button', { name: 'Actions for “Holiday teaser, final”' }).click()
  await page.getByRole('menuitem', { name: 'Delete' }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'Delete' }).click()
  // The open dialog hides the list from assistive tech, so wait for the confirmation.
  await expect(page.getByText('Deleted “Holiday teaser, final”')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Holiday teaser, final' })).toHaveCount(0)

  // The mock keeps its state across page loads, as a backend would.
  await page.reload()
  await expect(
    page.getByRole('link', { name: 'Lumen launch: 30s master', exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('link', { name: 'Holiday teaser, final' })).toHaveCount(0)
})
