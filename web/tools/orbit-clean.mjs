// Clean hero screenshots — hides the viewer UI chrome (fixed-position overlays) and captures a
// fixed set of (azimuth, elevation) angles. Same camera math + GPU caveat as orbit-shots.mjs.
// Usage:  node web/tools/orbit-clean.mjs <sceneId> <outDir>
import { chromium } from 'playwright'
import fs from 'fs'
import path from 'path'

const scene = process.argv[2]
const outDir = path.resolve(process.argv[3] || `orbit/clean_${scene}`)
if (!scene) { console.error('usage: node orbit-clean.mjs <sceneId> <outDir>'); process.exit(1) }
const BASE = process.env.VIEWER_BASE || 'http://localhost:5173'
const RAD = 0.92
// matched hero angles: [azimuth deg, elevation frac of diagonal above center]
const ANGLES = [[90, 0.28], [200, 0.26], [270, 0.30], [315, 0.22]]
fs.mkdirSync(outDir, { recursive: true })

const browser = await chromium.launch({ headless: false })
const page = await browser.newPage({ viewport: { width: 1280, height: 960 } })
page.setDefaultTimeout(120000)
page.on('dialog', d => d.dismiss().catch(() => {}))
await page.goto(`${BASE}/?scene=${scene}`, { waitUntil: 'load' })
await page.waitForFunction(() => window.__viewer && window.__viewer.camera, null, { timeout: 60000 })
await page.waitForTimeout(9000)

// hide every fixed-position overlay (home link, level panel, walk pad, hint) so only the canvas shows
await page.evaluate(() => {
  for (const el of Array.from(document.body.children)) {
    const cs = getComputedStyle(el)
    if (cs.position === 'fixed' || cs.position === 'absolute') el.style.display = 'none'
  }
})

const meta = await page.evaluate(async (s) => {
  const r = await fetch(`/scenes/${s}/scene.json`); const j = await r.json()
  return { bbox: j.bbox, up: (Array.isArray(j.up) && j.up.length === 3) ? j.up : [0, 1, 0] }
}, scene)
const bb = meta.bbox
const c = bb[0].map((lo, i) => (lo + bb[1][i]) / 2)
const diag = Math.hypot(...bb[1].map((hi, i) => hi - bb[0][i]))

for (const [az, lift] of ANGLES) {
  await page.evaluate(({ c, up, az, diag, rad, lift }) => {
    const v = window.__viewer, U = up
    let h = [0, 0, 1]
    const d = h[0] * U[0] + h[1] * U[1] + h[2] * U[2]
    h = [h[0] - d * U[0], h[1] - d * U[1], h[2] - d * U[2]]
    const hn = Math.hypot(...h); h = h.map(x => x / hn)
    const w = [U[1] * h[2] - U[2] * h[1], U[2] * h[0] - U[0] * h[2], U[0] * h[1] - U[1] * h[0]]
    const a = az * Math.PI / 180
    const dir = [h[0] * Math.cos(a) + w[0] * Math.sin(a), h[1] * Math.cos(a) + w[1] * Math.sin(a), h[2] * Math.cos(a) + w[2] * Math.sin(a)]
    const R = rad * diag, L = lift * diag
    v.camera.position.set(c[0] - dir[0] * R + U[0] * L, c[1] - dir[1] * R + U[1] * L, c[2] - dir[2] * R + U[2] * L)
    v.camera.up.set(U[0], U[1], U[2]); v.camera.lookAt(c[0], c[1], c[2]); v.camera.updateProjectionMatrix()
  }, { c, up: meta.up, az, diag, rad: RAD, lift })
  await page.waitForTimeout(900)
  await page.screenshot({ path: path.join(outDir, `az${String(az).padStart(3, '0')}.png`), timeout: 60000, animations: 'disabled' })
}
await browser.close()
console.log(`wrote ${ANGLES.length} clean shots -> ${outDir}`)
