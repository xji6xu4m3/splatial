import { createViewer } from './splatViewer.js'
import { loadSceneMeta } from './sceneLoader.js'
import { placeObject } from './objects.js'
import * as THREE from 'three'

const app = document.getElementById('app')
const _rawScene = new URLSearchParams(location.search).get('scene') || 'room1'
const sceneId = /^[a-zA-Z0-9_-]+$/.test(_rawScene) ? _rawScene : 'room1'

async function boot() {
  const { scene, objects } = await loadSceneMeta(sceneId)
  if (!/^[a-zA-Z0-9_.-]+\.ply$/.test(scene.ply)) throw new Error('Invalid ply path')
  // Start the camera near the capture origin (AnySplat's first-frame pose = world origin),
  // looking toward the scene centre — i.e. roughly "standing where you filmed", which is
  // where a feed-forward splat looks best. Drag to look, scroll/pinch to move through it.
  const c = (scene.bbox && scene.bbox.length === 2)
    ? scene.bbox[0].map((lo, i) => (lo + scene.bbox[1][i]) / 2)
    : [0, 0, 0]
  const viewer = await createViewer(app, `/scenes/${sceneId}/${scene.ply}`, {
    cameraPosition: [0, 0, 0.1],
    lookAt: c,
  })
  // Dark neutral background so thin/empty splat areas read as depth, not glaring white.
  viewer.renderer.setClearColor(new THREE.Color(0x0d0d12), 1)
  viewer.threeScene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 1.2))
  for (const o of objects) {
    // GLB paths in objects.json are repo-relative (e.g. assets/chair.glb) -> serve as /assets/...
    await placeObject(viewer.threeScene, { ...o, glb: '/' + o.glb })
  }
  window.__viewer = viewer
  window.__objectCount = objects.length
}

boot().catch((e) => { console.error('viewer failed', e) })
