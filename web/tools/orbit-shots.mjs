// Free-orbit screenshot dome — the realism ruler.
//
// Held-out PSNR is ON-TRAJECTORY interpolation and does NOT predict free-orbit quality (see
// docs/analysis/2026-06-04-postopt-vs-feedforward-rootcause.md §2). The deployment view
// distribution is the viewer's free orbit AROUND the room. This tool renders a scene from a
// canonical, deterministic dome of cameras (azimuth ring at two elevations) so two scenes can be
// A/B'd from the IDENTICAL camera set — the visual realism metric the analysis recommends.
//
// Usage:  node web/tools/orbit-shots.mjs <sceneId> [outDir] [nAz]
//   node web/tools/orbit-shots.mjs hires_full
//   node web/tools/orbit-shots.mjs hires_mcmc_or03 orbit/hires_mcmc_or03 8
// Requires the dev server running (npm run dev) at http://localhost:5173. Viewer only (never :8090).

import { chromium } from 'playwright'
import fs from 'fs'
import path from 'path'

const scene = process.argv[2]
if (!scene) { console.error('usage: node orbit-shots.mjs <sceneId> [outDir] [nAz]'); process.exit(1) }
const outDir = path.resolve(process.argv[3] || `orbit/${scene}`)
const nAz = parseInt(process.argv[4] || '8', 10)
const BASE = process.env.VIEWER_BASE || 'http://localhost:5173'
const ELEVATIONS = [0.18, 0.55]   // fraction of bbox diagonal above center: eye-level ring + high ring
const RAD = 0.95                  // orbit radius as fraction of bbox diagonal
fs.mkdirSync(outDir, { recursive: true })

// Headed on the host X display ($DISPLAY) so WebGL uses the real GPU — headless Chromium falls back
// to software rendering (swiftshader) and cannot rasterize millions of splats before screenshot timeout.
const browser = await chromium.launch({ headless: false })
const page = await browser.newPage({ viewport: { width: 1280, height: 960 } })
page.setDefaultTimeout(120000)
page.on('dialog', d => d.dismiss().catch(() => {}))   // safety: never accept any dialog
await page.goto(`${BASE}/?scene=${scene}`, { waitUntil: 'load' })
await page.waitForFunction(() => window.__viewer && window.__viewer.camera, null, { timeout: 60000 })
await page.waitForTimeout(9000)   // let the PLY load + GPU sort settle

const meta = await page.evaluate(async (s) => {
  const r = await fetch(`/scenes/${s}/scene.json`)
  const j = await r.json()
  return { bbox: j.bbox, up: (Array.isArray(j.up) && j.up.length === 3) ? j.up : [0, 1, 0] }
}, scene)

const bb = meta.bbox
const c = bb[0].map((lo, i) => (lo + bb[1][i]) / 2)
const diag = Math.hypot(...bb[1].map((hi, i) => hi - bb[0][i]))

const shots = []
for (const elev of ELEVATIONS) {
  for (let i = 0; i < nAz; i++) {
    const az = (360 / nAz) * i
    await page.evaluate(({ c, up, az, diag, rad, lift }) => {
      const v = window.__viewer
      const U = up
      // a horizontal axis perpendicular to up, and its in-plane orthogonal -> azimuth ring basis
      let h = [0, 0, 1]
      const d = h[0] * U[0] + h[1] * U[1] + h[2] * U[2]
      h = [h[0] - d * U[0], h[1] - d * U[1], h[2] - d * U[2]]
      const hn = Math.hypot(...h); h = h.map(x => x / hn)
      const w = [U[1] * h[2] - U[2] * h[1], U[2] * h[0] - U[0] * h[2], U[0] * h[1] - U[1] * h[0]]
      const a = az * Math.PI / 180
      const dir = [h[0] * Math.cos(a) + w[0] * Math.sin(a),
                   h[1] * Math.cos(a) + w[1] * Math.sin(a),
                   h[2] * Math.cos(a) + w[2] * Math.sin(a)]
      const R = rad * diag, L = lift * diag
      v.camera.position.set(c[0] - dir[0] * R + U[0] * L,
                            c[1] - dir[1] * R + U[1] * L,
                            c[2] - dir[2] * R + U[2] * L)
      v.camera.up.set(U[0], U[1], U[2])
      v.camera.lookAt(c[0], c[1], c[2])
      v.camera.updateProjectionMatrix()
    }, { c, up: meta.up, az, diag, rad: RAD, lift: elev })
    await page.waitForTimeout(900)   // re-sort for the new view
    const file = path.join(outDir, `e${Math.round(elev * 100)}_az${String(Math.round(az)).padStart(3, '0')}.png`)
    await page.screenshot({ path: file, timeout: 60000, animations: 'disabled' })
    shots.push(file)
  }
}
await browser.close()
console.log(`wrote ${shots.length} orbit frames -> ${outDir}`)
