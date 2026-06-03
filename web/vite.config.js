import { defineConfig } from 'vite'

// Cross-origin isolation (COOP + COEP) makes SharedArrayBuffer available, which lets the
// Gaussian-splat sort worker read splat data without copying the whole buffer on every view
// change — the fix for the multi-second stall when leveling/turning ~1M splats. We use
// COEP:credentialless (not require-corp) so the cross-origin, no-credentials POST to the
// capture server's /up endpoint (port 8090) still works for saving a leveled up-vector.
const crossOriginIsolation = {
  name: 'cross-origin-isolation',
  configureServer(server) {
    server.middlewares.use((_req, res, next) => {
      res.setHeader('Cross-Origin-Opener-Policy', 'same-origin')
      res.setHeader('Cross-Origin-Embedder-Policy', 'credentialless')
      next()
    })
  },
}

export default defineConfig({
  plugins: [crossOriginIsolation],
  server: { port: 5173, fs: { allow: ['..'] } },  // allow serving ../scenes
})
