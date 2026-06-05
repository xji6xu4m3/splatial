import * as THREE from 'three'

/**
 * Manual "level the horizon" control. Auto-up (from AnySplat poses) is approximate for tight
 * object orbits, so this lets you rotate the whole view until the floor/table is horizontal,
 * then persist it. Roll spins the up axis around the view direction; Tilt rotates it toward/away.
 * Hold a button to keep rotating. Save writes the up vector back to the scene's scene.json.
 */
export function enableLevel(viewer, sceneId) {
  const cam = viewer.camera
  const target = viewer.controls.target
  const fwd = new THREE.Vector3(), right = new THREE.Vector3()
  const STEP = 0.03 // radians per tick (~1.7°)

  function applyUp(axis, ang) {
    cam.up.applyAxisAngle(axis, ang).normalize()
    cam.lookAt(target)
    if (viewer.controls.update) viewer.controls.update()
    readout.textContent = `up [${cam.up.x.toFixed(2)}, ${cam.up.y.toFixed(2)}, ${cam.up.z.toFixed(2)}]`
  }
  const roll = (s) => { fwd.subVectors(target, cam.position).normalize(); applyUp(fwd, s * STEP) }
  const tilt = (s) => {
    fwd.subVectors(target, cam.position).normalize()
    right.crossVectors(fwd, cam.up).normalize()
    applyUp(right, s * STEP)
  }

  // --- panel (left edge, vertically centered) ---
  const panel = document.createElement('div')
  panel.style.cssText = 'position:fixed;left:12px;top:50%;transform:translateY(-50%);z-index:1000;' +
    'display:flex;flex-direction:column;gap:6px;width:120px;font:600 13px system-ui;color:#fff'
  const title = document.createElement('div')
  title.textContent = '🧭 Level view'
  title.style.cssText = 'opacity:.85;text-align:center'
  const readout = document.createElement('div')
  readout.style.cssText = 'font:11px ui-monospace,monospace;color:#bbb;text-align:center;min-height:14px'

  // hold-to-repeat button
  const hold = (label, fn) => {
    const b = document.createElement('button')
    b.textContent = label
    b.style.cssText = 'padding:9px;border:0;border-radius:8px;background:rgba(94,53,177,.85);' +
      'color:#fff;font:600 14px system-ui;touch-action:none;user-select:none'
    let t = null
    const start = (e) => { e.preventDefault(); fn(); t = setInterval(fn, 60) }
    const stop = () => { if (t) { clearInterval(t); t = null } }
    b.addEventListener('pointerdown', start)
    for (const ev of ['pointerup', 'pointerleave', 'pointercancel']) b.addEventListener(ev, stop)
    return b
  }
  const row = (...kids) => { const d = document.createElement('div'); d.style.cssText = 'display:flex;gap:6px'; kids.forEach(k => { k.style.flex = '1'; d.append(k) }); return d }

  const save = document.createElement('button')
  save.textContent = '💾 Save level'
  save.style.cssText = 'padding:9px;border:0;border-radius:8px;background:#2e7d32;color:#fff;font:600 13px system-ui'
  save.addEventListener('click', () => {
    save.textContent = 'saving…'
    fetch(`/up/${encodeURIComponent(sceneId)}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ up: [cam.up.x, cam.up.y, cam.up.z] }),
    }).then(r => r.ok ? (save.textContent = '✓ saved') : r.text().then(t => { save.textContent = '✗ ' + t }))
      .catch(() => { save.textContent = '✗ failed' })
      .finally(() => setTimeout(() => { save.textContent = '💾 Save level' }, 2000))
  })

  panel.append(
    title,
    row(hold('⟲', () => roll(1)), hold('⟳', () => roll(-1))),
    row(hold('⤒', () => tilt(1)), hold('⤓', () => tilt(-1))),
    save, readout,
  )
  document.body.appendChild(panel)
  readout.textContent = `up [${cam.up.x.toFixed(2)}, ${cam.up.y.toFixed(2)}, ${cam.up.z.toFixed(2)}]`
}
