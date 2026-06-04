import { test, expect } from '@playwright/test'

// Heavy integration test: loads the real ~75 MB / 1.1 M-splat scene. Software-WebGL
// CI runners are slow, so timeouts are generous. (Fast unit coverage lives in pytest.)
test('viewer actually renders the splat scene', async ({ page }) => {
  test.setTimeout(180000)
  const errors = []
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  await page.goto('/?scene=pet1')
  await page.waitForFunction(() => window.__viewer !== undefined, { timeout: 150000 })

  const canvas = page.locator('canvas')
  await expect(canvas.first()).toBeVisible()

  // CRITICAL: a visible canvas is NOT proof the splats draw — a black canvas is still
  // "visible" and logs no errors. (That gap let a zero-draw-call regression ship once.)
  // Assert the renderer issues at least one draw call once the splat mesh is ready.
  await page.waitForFunction(() => {
    const v = window.__viewer
    return v && v.splatRenderReady === true &&
      (v.renderer?.info?.render?.calls || 0) > 0 &&
      (v.splatMesh?.getSplatCount?.() || 0) > 0
  }, { timeout: 150000 })

  expect(errors, errors.join('\n')).toHaveLength(0)
})
