import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  root: __dirname,
  plugins: [react()],
  clearScreen: false,
  base: './',
  optimizeDeps: {
    include: ['@excalidraw/excalidraw'],
  },
  build: {
    chunkSizeWarningLimit: 2048,
    outDir: path.join(__dirname, 'dist'),
  },
  server: {
    port: 3001,
    strictPort: true,
    host: true,
    proxy: {
      '/api/excalidraw/sync': {
        target: 'ws://localhost:5858',
        ws: true,
        rewrite: (path) => path.replace(/^\/api\/excalidraw\/sync/, ''),
      },
      '/api': {
        target: 'http://localhost:8000',
        ws: true,
      },
      '/download': {
        target: 'http://localhost:8000',
        ws: true,
      },
      '/auth': {
        target: 'http://localhost:8000',
        ws: true,
      },
      '/upload': {
        target: 'http://localhost:8000',
        ws: true,
      },
    },
  },
})