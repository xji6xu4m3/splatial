import * as GaussianSplats3D from '@mkkellogg/gaussian-splats-3d'

export async function createViewer(container, plyUrl, opts = {}) {
  const viewer = new GaussianSplats3D.Viewer({
    rootElement: container,
    cameraUp: opts.cameraUp || [0, 1, 0],
    initialCameraPosition: opts.cameraPosition || [0, 0, 4],
    initialCameraLookAt: opts.lookAt || [0, 0, 0],
    sphericalHarmonicsDegree: 0,
    // Avoid SharedArrayBuffer (needs cross-origin isolation / COOP+COEP headers).
    // Disabling shared-memory workers makes the viewer work on a plain dev server.
    sharedMemoryForWorkers: false,
  })
  await viewer.addSplatScene(plyUrl, { showLoadingUI: true })
  // Cap render resolution. Phones report devicePixelRatio 2–3; rendering ~1M splats at
  // native density overheats the GPU and tanks FPS. 1.25 keeps it readable but ~4–6x cheaper.
  const cap = opts.maxPixelRatio ?? 1.25
  if (viewer.renderer?.setPixelRatio) viewer.renderer.setPixelRatio(Math.min(devicePixelRatio || 1, cap))
  viewer.start()
  return viewer  // viewer.threeScene is the THREE.Scene we add objects to
}
