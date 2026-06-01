import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

const loader = new GLTFLoader()

export function loadGLB(url) {
  return new Promise((res, rej) => loader.load(url, (g) => res(g.scene), undefined, rej))
}

export function applyTransform(obj3d, t) {
  obj3d.position.fromArray(t.position)
  obj3d.quaternion.fromArray(t.rotation)   // [x,y,z,w]
  obj3d.scale.fromArray(t.scale)
}

export async function placeObject(threeScene, sceneObject) {
  const root = await loadGLB(sceneObject.glb)
  applyTransform(root, sceneObject.transform)
  if (sceneObject.material_overrides?.color) {
    const [r, g, b] = sceneObject.material_overrides.color
    root.traverse((m) => { if (m.isMesh) m.material = new THREE.MeshStandardMaterial({ color: new THREE.Color(r, g, b) }) })
  }
  root.userData.objectId = sceneObject.id
  threeScene.add(root)
  return root
}
