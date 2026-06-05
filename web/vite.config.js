import { defineConfig } from 'vite'

// Cross-origin isolation (COOP + COEP) makes SharedArrayBuffer available, which lets the
// Gaussian-splat sort worker read splat data without copying the whole buffer on every view
// change — the fix for the multi-second stall when leveling/turning ~1M splats. COEP is
// credentialless (not require-corp); in production the viewer + capture + /up are all served
// same-origin by modules/serve (which sets the same COOP/COEP headers), so there is no CORS.
// This dev server mirrors those headers so SharedArrayBuffer works under `npm run dev` too.
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
  // Built assets load from /view/ so they don't collide with the server's /assets/ GLB route.
  // NOTE for `npm run dev`: the app is now served at http://localhost:5173/view/?scene=<id>
  // (not bare /). The "← New scan" home link points at / and only resolves under modules/serve.
  base: '/view/',
  plugins: [crossOriginIsolation],
  // host:true binds 0.0.0.0 so a phone on the LAN can reach the dev viewer directly. Without it
  // Vite listens on localhost only and the phone gets connection-refused. (In production the
  // viewer is served by modules/serve, not this dev server.)
  server: { host: true, port: 5173, fs: { allow: ['..'] } },  // allow serving ../scenes
})
