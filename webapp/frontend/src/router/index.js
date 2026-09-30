import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/HomeView.vue'),
    meta: { title: 'ホーム' },
  },
  {
    path: '/projects/:projectId',
    name: 'Project',
    component: () => import('@/views/ProjectView.vue'),
    meta: { title: 'プロジェクト' },
  },
  {
    path: '/videos/:videoId',
    name: 'VideoEditor',
    component: () => import('@/views/VideoEditorView.vue'),
    meta: { title: '動画編集' },
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { title: '設定' },
  },
]

// Vite の import.meta.env.BASE_URL を渡すことで、サブパス運用時（例: /ai-mov-studio/）でも
// ルーティング履歴が正しく解決されるようにする。未指定時は '/'（通常運用）となる。
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

// ページタイトルを自動設定
router.afterEach((to) => {
  document.title = to.meta.title
    ? `${to.meta.title} — AI Mov-Studio`
    : 'AI Mov-Studio'
})

export default router
