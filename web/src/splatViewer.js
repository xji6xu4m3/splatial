import * as GaussianSplats3D from '@mkkellogg/gaussian-splats-3d'

export async function createViewer(container, plyUrl, opts = {}) {
  const viewer = new GaussianSplats3D.Viewer({
    rootElement: container,
    cameraUp: opts.cameraUp || [0, 1, 0],
    initialCameraPosition: opts.cameraPosition || [0, 0, 4],
    initialCameraLookAt: opts.lookAt || [0, 0, 0],
    sphericalHarmonicsDegree: 0,
    // SharedArrayBuffer lets the sort worker read splat data in place instead of copying the
    // whole buffer on every view change — this kills the multi-second leveling/turning stall.
    // It needs cross-origin isolation (COOP + COEP), which vite.config.js sets via headers.
    // NOTE: gpuAcceleratedSort was tried instead but rendered ZERO draw calls (black screen)
    // on this build — do NOT re-enable it without a *visual* render check (a black canvas
    // still reports 60 FPS, so frame-rate alone is not proof the splats are drawing).
    sharedMemoryForWorkers: true,
  })
  await viewer.addSplatScene(plyUrl, { showLoadingUI: true })
  // Cap render resolution. Phones report devicePixelRatio 2–3; rendering ~1M splats at
  // native density overheats the GPU and tanks FPS. 1.25 keeps it readable but ~4–6x cheaper.
  const cap = opts.maxPixelRatio ?? 1.25
  if (viewer.renderer?.setPixelRatio) viewer.renderer.setPixelRatio(Math.min(devicePixelRatio || 1, cap))
  viewer.start()
  return viewer  // viewer.threeScene is the THREE.Scene we add objects to
}
