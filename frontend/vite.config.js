import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev, forward /api/* to the FastAPI backend on port 8000 so the React
// app (port 5173) can call it without CORS or port issues.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
