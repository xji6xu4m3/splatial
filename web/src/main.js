import { createViewer } from './splatViewer.js'
import { loadSceneMeta } from './sceneLoader.js'
import { placeObject } from './objects.js'
import { enableWalk } from './walk.js'
import { enableLevel } from './level.js'
import * as THREE from 'three'

const app = document.getElementById('app')
const _rawScene = new URLSearchParams(location.search).get('scene') || 'room1'
const sceneId = /^[a-zA-Z0-9_-]+$/.test(_rawScene) ? _rawScene : 'room1'

// Persistent "New scan" button -> back to the capture page (always available).
const home = document.createElement('a')
home.textContent = '← New scan'
home.href = '/'
home.style.cssText = 'position:fixed;top:12px;left:12px;z-index:1000;padding:10px 14px;' +
  'background:rgba(94,53,177,.92);color:#fff;border-radius:8px;font:600 15px system-ui;' +
  'text-decoration:none'
document.body.appendChild(home)

// Pick a camera position that frames the whole bbox: centre, backed off along a horizontal
// direction (perpendicular to the up axis) by ~1.3× the diagonal, raised ~0.25× the diagonal.
function frameCamera(center, bbox, up) {
  const U = new THREE.Vector3(up[0], up[1], up[2]).normalize()
  const diag = (bbox && bbox.length === 2)
    ? Math.hypot(...bbox[1].map((hi, i) => hi - bbox[0][i]))
    : 3
  // Horizontal forward = the world axis least aligned with up, with the up-component removed
  // (so it lies in the ground plane). Gives a natural eye-level vantage on a tilted scene.
  const axes = [new THREE.Vector3(0, 0, 1), new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 1, 0)]
  const base = axes.reduce((a, b) => (Math.abs(a.dot(U)) <= Math.abs(b.dot(U)) ? a : b))
  const horiz = base.clone().addScaledVector(U, -base.dot(U)).normalize()
  const C = new THREE.Vector3(center[0], center[1], center[2])
  const pos = C.clone().addScaledVector(horiz, -1.3 * diag).addScaledVector(U, 0.25 * diag)
  return [pos.x, pos.y, pos.z]
}

async function boot() {
  const { scene, objects } = await loadSceneMeta(sceneId)
  if (!/^[a-zA-Z0-9_.-]+\.ply$/.test(scene.ply)) throw new Error('Invalid ply path')
  // Use the scene's recovered gravity-up (from AnySplat's predicted cameras) as the camera/orbit
  // up axis, so the floor renders level instead of tilted. Falls back to +Y for legacy scenes.
  const up = (Array.isArray(scene.up) && scene.up.length === 3) ? scene.up : [0, 1, 0]
  // Frame the WHOLE scene on load. AnySplat puts camera-0 at the world origin, which usually
  // sits INSIDE the point cloud — spawning there shows a wall of near splats and reads as "empty"
  // until you fly out. Instead, look at the bbox centre from outside: back off along a horizontal
  // axis (perpendicular to up) by ~1.3× the bbox diagonal, raised a bit. Guarantees the object is
  // on-screen regardless of how the scan was framed.
  const c = (scene.bbox && scene.bbox.length === 2)
    ? scene.bbox[0].map((lo, i) => (lo + scene.bbox[1][i]) / 2)
    : [0, 0, 0]
  const camPos = frameCamera(c, scene.bbox, up)
  const viewer = await createViewer(app, `/scenes/${sceneId}/${scene.ply}`, {
    cameraPosition: camPos,
    lookAt: c,
    cameraUp: up,
  })
  // Dark neutral background so thin/empty splat areas read as depth, not glaring white.
  viewer.renderer.setClearColor(new THREE.Color(0x0d0d12), 1)
  viewer.threeScene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 1.2))
  for (const o of objects) {
    // GLB paths in objects.json are repo-relative (e.g. assets/chair.glb) -> serve as /assets/...
    await placeObject(viewer.threeScene, { ...o, glb: '/' + o.glb })
  }
  // Walk/fly inspection: extent from the scene bbox sets the move speed.
  const extent = (scene.bbox && scene.bbox.length === 2)
    ? Math.hypot(...scene.bbox[1].map((hi, i) => hi - scene.bbox[0][i]))
    : 3
  enableWalk(viewer, extent, up)
  enableLevel(viewer, sceneId)
  window.__viewer = viewer
  window.__objectCount = objects.length
}

boot().catch((e) => { console.error('viewer failed', e) })
