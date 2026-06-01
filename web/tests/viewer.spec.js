import { test, expect } from '@playwright/test'

// Heavy integration test: loads the real ~113 MB / 1.66 M-splat scene. Software-WebGL
// CI runners are slow, so timeouts are generous. (Fast unit coverage lives in pytest.)
test('viewer loads splat + object without console errors', async ({ page }) => {
  test.setTimeout(180000)
  const errors = []
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  await page.goto('/?scene=room1')
  await page.waitForFunction(() => window.__viewer !== undefined, { timeout: 150000 })
  const count = await page.evaluate(() => window.__objectCount)
  expect(count).toBeGreaterThanOrEqual(1)
  const canvas = page.locator('canvas')
  await expect(canvas.first()).toBeVisible()
  expect(errors, errors.join('\n')).toHaveLength(0)
})
