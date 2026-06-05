import { defineConfig } from '@playwright/test'
export default defineConfig({
  // Vite serves the viewer under base '/view/', so the probe + baseURL must include it.
  webServer: { command: 'npm run dev', url: 'http://localhost:5173/view/', reuseExistingServer: true },
  use: { baseURL: 'http://localhost:5173/view/' },
})
