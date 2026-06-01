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
  viewer.start()
  return viewer  // viewer.threeScene is the THREE.Scene we add objects to
}
