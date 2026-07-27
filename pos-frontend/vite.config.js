import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Fixed port so it never collides with admin-frontend's default 5173 —
  // both can run at once during development against the same Django API.
  server: {
    port: 5174,
  },
})
