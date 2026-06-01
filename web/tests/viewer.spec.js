import { test, expect } from '@playwright/test'

test('viewer loads splat + object without console errors', async ({ page }) => {
  const errors = []
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  await page.goto('/?scene=room1')
  await page.waitForFunction(() => window.__viewer !== undefined, { timeout: 30000 })
  const count = await page.evaluate(() => window.__objectCount)
  expect(count).toBeGreaterThanOrEqual(1)
  const canvas = page.locator('canvas')
  await expect(canvas.first()).toBeVisible()
  expect(errors, errors.join('\n')).toHaveLength(0)
})
