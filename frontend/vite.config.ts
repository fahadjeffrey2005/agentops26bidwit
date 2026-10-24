import path from 'node:path'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname ?? path.dirname(fileURLToPath(import.meta.url)), './src') } },
  server: { host: '127.0.0.1', port: 5174, strictPort: true, proxy: { '/api': 'http://127.0.0.1:8000' } },
})
