import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端默认地址；如后端换了端口，改这里的 target 即可。
const API_TARGET = 'http://127.0.0.1:8080'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5400,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
})
