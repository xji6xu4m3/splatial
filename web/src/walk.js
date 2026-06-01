import * as THREE from 'three'

/**
 * First-person "walk" controls layered on the splat viewer's orbit rig.
 * Moving translates BOTH the camera and the orbit target along the view direction,
 * so you fly/walk through the scene while drag-to-look and pinch-zoom still work.
 *
 * Desktop: W/A/S/D move, Q/E (or Space/Shift) down/up.
 * Mobile: on-screen D-pad (hold to move). Drag with one finger to look.
 */
export function enableWalk(viewer, sceneExtent = 3) {
  const cam = viewer.camera
  const target = viewer.controls.target
  const speed = Math.max(0.02, sceneExtent * 0.012) // per-frame step, scaled to scene size
  const keys = { fwd: 0, back: 0, left: 0, right: 0, up: 0, down: 0 }

  const KEYMAP = {
    KeyW: 'fwd', ArrowUp: 'fwd', KeyS: 'back', ArrowDown: 'back',
    KeyA: 'left', ArrowLeft: 'left', KeyD: 'right', ArrowRight: 'right',
    KeyE: 'up', Space: 'up', KeyQ: 'down', ShiftLeft: 'down',
  }
  addEventListener('keydown', (e) => { const m = KEYMAP[e.code]; if (m) { keys[m] = 1; e.preventDefault() } })
  addEventListener('keyup', (e) => { const m = KEYMAP[e.code]; if (m) keys[m] = 0 })

  // --- per-frame movement loop ---
  const fwd = new THREE.Vector3(), right = new THREE.Vector3()
  const worldUp = new THREE.Vector3(0, 1, 0), move = new THREE.Vector3()
  function tick() {
    fwd.subVectors(target, cam.position); fwd.y *= 1; fwd.normalize()
    right.crossVectors(fwd, worldUp).normalize()
    move.set(0, 0, 0)
    move.addScaledVector(fwd, (keys.fwd - keys.back) * speed)
    move.addScaledVector(right, (keys.right - keys.left) * speed)
    move.addScaledVector(worldUp, (keys.up - keys.down) * speed)
    if (move.lengthSq() > 0) { cam.position.add(move); target.add(move) }
    requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)

  // --- mobile D-pad ---
  const pad = document.createElement('div')
  pad.style.cssText = 'position:fixed;bottom:18px;left:50%;transform:translateX(-50%);' +
    'z-index:1000;display:grid;grid-template-columns:repeat(3,52px);grid-gap:6px;' +
    'touch-action:none;user-select:none;opacity:.9'
  const mk = (label, k, col, rowExtra = '') => {
    const b = document.createElement('button')
    b.textContent = label
    b.style.cssText = 'height:52px;border:0;border-radius:10px;background:rgba(94,53,177,.85);' +
      'color:#fff;font-size:20px;font-weight:700;' + `grid-column:${col};` + rowExtra
    const on = (e) => { keys[k] = 1; e.preventDefault() }
    const off = () => { keys[k] = 0 }
    b.addEventListener('pointerdown', on); b.addEventListener('pointerup', off)
    b.addEventListener('pointerleave', off); b.addEventListener('pointercancel', off)
    return b
  }
  pad.append(
    mk('▲', 'fwd', 2),
    mk('◀', 'left', 1), mk('▼', 'back', 2), mk('▶', 'right', 3),
    mk('▼up', 'down', 1), mk('▲up', 'up', 3),
  )
  document.body.appendChild(pad)

  // --- one-line hint ---
  const hint = document.createElement('div')
  hint.textContent = 'WASD / D-pad to walk · drag to look · scroll/pinch to zoom'
  hint.style.cssText = 'position:fixed;top:12px;right:12px;z-index:1000;padding:8px 12px;' +
    'background:rgba(0,0,0,.55);color:#ddd;border-radius:8px;font:13px system-ui'
  document.body.appendChild(hint)
}
