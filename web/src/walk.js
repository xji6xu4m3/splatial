import * as THREE from 'three'

/**
 * First-person "walk" controls layered on the splat viewer's orbit rig.
 * Moving translates BOTH the camera and the orbit target along the view direction;
 * turning yaws the orbit target around the camera. Drag-to-look and pinch-zoom still work.
 *
 * Desktop:
 *   W/S or ↑/↓ ... move forward / back
 *   A/D ......... strafe left / right
 *   Q/E or ←/→ . turn (yaw) left / right
 *   Space/Shift  move up / down
 * Mobile: on-screen pad — ▲▼ move, ◀▶ strafe, ↺↻ turn (hold to act). Drag a finger to look.
 */
export function enableWalk(viewer, sceneExtent = 3, up = [0, 1, 0]) {
  const cam = viewer.camera
  const target = viewer.controls.target
  // OrbitControls binds W/A/S/D and arrow keys to PANNING (keys:{LEFT:KeyA,...}, enablePan:true).
  // walk.js owns all translation, so leaving pan on means every move key fires twice — e.g. W
  // moves forward AND pans the camera up, which reads as the view drifting vertically. Disable it.
  if (viewer.controls) viewer.controls.enablePan = false
  const speed = Math.max(0.02, sceneExtent * 0.012) // per-frame step, scaled to scene size
  const turnSpeed = 0.025 // radians/frame
  const keys = { fwd: 0, back: 0, left: 0, right: 0, up: 0, down: 0, turnL: 0, turnR: 0 }

  const KEYMAP = {
    KeyW: 'fwd', ArrowUp: 'fwd', KeyS: 'back', ArrowDown: 'back',
    KeyA: 'left', KeyD: 'right',
    KeyQ: 'turnL', ArrowLeft: 'turnL', KeyE: 'turnR', ArrowRight: 'turnR',
    Space: 'up', ShiftLeft: 'down', ShiftRight: 'down',
  }
  addEventListener('keydown', (e) => { const m = KEYMAP[e.code]; if (m) { keys[m] = 1; e.preventDefault() } })
  addEventListener('keyup', (e) => { const m = KEYMAP[e.code]; if (m) keys[m] = 0 })

  // --- per-frame movement loop ---
  const fwd = new THREE.Vector3(), right = new THREE.Vector3()
  // Gravity-up from the scene (AnySplat poses), so yaw and strafe stay level on a tilted scan.
  const worldUp = new THREE.Vector3(up[0], up[1], up[2]).normalize(), move = new THREE.Vector3()
  const view = new THREE.Vector3()
  function tick() {
    // Turn: yaw the view vector (target relative to camera) around world-up, in place.
    const turn = (keys.turnL - keys.turnR) * turnSpeed
    if (turn !== 0) {
      view.subVectors(target, cam.position).applyAxisAngle(worldUp, turn)
      target.copy(cam.position).add(view)
    }
    // Move: translate camera + target together along the (horizontal) view basis.
    fwd.subVectors(target, cam.position).normalize()
    right.crossVectors(fwd, worldUp).normalize()
    move.set(0, 0, 0)
    move.addScaledVector(fwd, (keys.fwd - keys.back) * speed)
    move.addScaledVector(right, (keys.right - keys.left) * speed)
    move.addScaledVector(worldUp, (keys.up - keys.down) * speed)
    if (move.lengthSq() > 0) { cam.position.add(move); target.add(move) }
    requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)

  // --- mobile on-screen pad ---
  const pad = document.createElement('div')
  pad.style.cssText = 'position:fixed;bottom:18px;left:50%;transform:translateX(-50%);' +
    'z-index:1000;display:grid;grid-template-columns:repeat(3,52px);grid-gap:6px;' +
    'touch-action:none;user-select:none;opacity:.9'
  const mk = (label, k, col) => {
    const b = document.createElement('button')
    b.textContent = label
    b.style.cssText = 'height:52px;border:0;border-radius:10px;background:rgba(94,53,177,.85);' +
      'color:#fff;font-size:20px;font-weight:700;' + `grid-column:${col};`
    const on = (e) => { keys[k] = 1; e.preventDefault() }
    const off = () => { keys[k] = 0 }
    b.addEventListener('pointerdown', on); b.addEventListener('pointerup', off)
    b.addEventListener('pointerleave', off); b.addEventListener('pointercancel', off)
    return b
  }
  pad.append(
    mk('↺', 'turnL', 1), mk('▲', 'fwd', 2), mk('↻', 'turnR', 3),
    mk('◀', 'left', 1), mk('▼', 'back', 2), mk('▶', 'right', 3),
  )
  document.body.appendChild(pad)

  // --- one-line hint ---
  const hint = document.createElement('div')
  hint.textContent = 'W/S move · A/D strafe · Q/E or ←/→ turn · drag to look · scroll/pinch zoom'
  hint.style.cssText = 'position:fixed;top:12px;right:12px;z-index:1000;padding:8px 12px;' +
    'background:rgba(0,0,0,.55);color:#ddd;border-radius:8px;font:13px system-ui'
  document.body.appendChild(hint)
}
