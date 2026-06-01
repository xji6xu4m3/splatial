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
  const viewer = await createViewer(app, `/scenes/${sceneId}/${scene.ply}`)
  viewer.threeScene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 1.2))
  for (const o of objects) {
    // GLB paths in objects.json are repo-relative (e.g. assets/chair.glb) -> serve as /assets/...
    await placeObject(viewer.threeScene, { ...o, glb: '/' + o.glb })
  }
  window.__viewer = viewer
  window.__objectCount = objects.length
}

boot().catch((e) => { console.error('viewer failed', e) })
