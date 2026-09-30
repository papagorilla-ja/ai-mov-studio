import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import { fileURLToPath, URL } from 'node:url'

// 環境変数 BASE_PATH または BASE_URL からベースパスを取得（例: '/ai-mov-studio/'）。
// 末尾にスラッシュがない場合は Vite の仕様に合わせて補完し、未設定時は '/'（通常ルート）とする。
const rawBase = process.env.BASE_PATH || process.env.BASE_URL || '/'
const base = rawBase.endsWith('/') ? rawBase : `${rawBase}/`

export default defineConfig({
  base,
  plugins: [
    vue(),
    vuetify({ autoImport: true }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  // ローカル開発時: vite dev サーバーから api コンテナへのプロキシ
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
