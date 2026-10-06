import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 개발용: 프론트가 상대 경로(/api/...)로 부르면 백엔드(uvicorn, 8000)로 넘긴다.
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
})
