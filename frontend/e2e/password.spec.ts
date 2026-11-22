import { expect, test } from '@playwright/test'

test('asks for the password, then opens the page that was asked for', async ({ page }) => {
  await page.goto('/history?mock=password')
  const password = page.getByLabel('Password')
  await password.fill('wrong')
  await password.press('Enter')
  await expect(page.getByRole('alert')).toHaveText('That password is not right.')

  await password.fill('lumen')
  await password.press('Enter')

  await expect(page.getByRole('heading', { level: 1, name: 'History' })).toBeVisible()
  await expect(
    page.getByRole('link', { name: 'Lumen launch: 30s master', exact: true }),
  ).toBeVisible()
})
