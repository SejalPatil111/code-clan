import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Where the dev server forwards /api requests.
// - Local (non-Docker) development: the FastAPI server on 127.0.0.1:8000 (default).
// - Docker Compose: http://backend:8000 (the backend service name on the Docker network).
// Deliberately NOT prefixed with VITE_ so it is never exposed to browser code.
const apiProxyTarget = process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000'

// File-change events from Windows bind mounts do not reach Linux containers,
// so polling is enabled inside Docker for hot reload (WATCH_POLLING=true).
const usePolling = process.env.WATCH_POLLING === 'true'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    watch: usePolling ? { usePolling: true, interval: 300 } : undefined,
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
