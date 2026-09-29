import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'

/**
 * グローバル UI 状態ストア
 * スナックバー通知やサイドバー開閉など画面横断的な状態を管理する
 */
export const useUiStore = defineStore('ui', () => {
  const snackbar = reactive({
    show: false,
    message: '',
    color: 'success',
    timeout: 3000,
  })

  // 左サイドバー開閉状態 (デフォルトは開く、localStorage に保存)
  const sidebarOpen = ref(localStorage.getItem('ai_mov_sidebar_open') !== 'false')

  function toggleSidebar() {
    sidebarOpen.value = !sidebarOpen.value
    localStorage.setItem('ai_mov_sidebar_open', String(sidebarOpen.value))
  }

  function setSidebar(open) {
    sidebarOpen.value = open
    localStorage.setItem('ai_mov_sidebar_open', String(open))
  }

  function notify(message, color = 'success', timeout = 3000) {
    snackbar.message = message
    snackbar.color = color
    snackbar.timeout = timeout
    snackbar.show = true
  }

  function notifyError(message) {
    notify(message, 'error', 5000)
  }

  return { snackbar, sidebarOpen, toggleSidebar, setSidebar, notify, notifyError }
})
