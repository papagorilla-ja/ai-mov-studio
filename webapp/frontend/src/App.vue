<template>
  <v-app class="cyber-studio-app">
    <!-- グローバルナビゲーションドロワー (Cyber Studio Glass) -->
    <v-navigation-drawer
      v-model="sidebarOpen"
      width="250"
      class="glass-sidebar d-flex flex-column"
    >
      <!-- ブランド・ロゴヘッダー -->
      <div class="pa-3 px-3 d-flex align-center justify-space-between logo-header">
        <div class="d-flex align-center overflow-hidden flex-grow-1">
          <div class="logo-avatar-wrapper mr-2 flex-shrink-0">
            <img :src="logoUrl" alt="AI Mov-Studio Logo" class="logo-img" />
            <div class="logo-glow"></div>
          </div>
          <div class="overflow-hidden">
            <div class="font-weight-black logo-title" style="white-space: nowrap; font-size: 0.95rem; letter-spacing: -0.3px;">AI Mov-Studio</div>
          </div>
        </div>
        <!-- サイドバー折りたたみボタン -->
        <v-btn
          icon="mdi-chevron-left"
          variant="text"
          size="small"
          class="sidebar-toggle-btn flex-shrink-0"
          title="サイドバーを隠す (Ctrl+B)"
          @click="uiStore.toggleSidebar"
        />
      </div>

      <v-divider class="border-opacity-15 mb-3" />

      <!-- ナビゲーションリンク一覧 -->
      <v-list density="comfortable" nav class="px-3 flex-grow-1">
        <v-list-item
          prepend-icon="mdi-view-dashboard-outline"
          title="ホーム & 制作"
          value="home"
          :to="{ path: '/' }"
          exact
          class="nav-item mb-1"
          active-class="nav-item-active"
        />
        <v-list-item
          prepend-icon="mdi-tune-vertical"
          title="環境設定"
          value="settings"
          :to="{ path: '/settings' }"
          class="nav-item mb-1"
          active-class="nav-item-active"
        />
      </v-list>

      <!-- サイドバー下部: システムステータス情報 -->
      <div class="pa-3 ma-3 glass-status-badge rounded-lg">
        <div class="d-flex align-center justify-between mb-1">
          <span class="text-xxs font-weight-bold text-uppercase text-cyan">AI Core System</span>
          <span class="status-indicator-live"></span>
        </div>
        <div class="text-xxs text-medium-emphasis">
          Qwen3-TTS &amp; Local LLM Ready
        </div>
      </div>
    </v-navigation-drawer>

    <!-- サイドバー展開用エッジトグルボタン（非表示時に作業スペースを最大化しつつ即座に展開可能） -->
    <transition name="fade">
      <button
        v-if="!sidebarOpen"
        class="sidebar-edge-tab"
        title="サイドバーを表示 (Ctrl+B)"
        @click="uiStore.toggleSidebar"
      >
        <v-icon size="16">mdi-chevron-right</v-icon>
      </button>
    </transition>

    <!-- メインコンテンツ領域 -->
    <v-main class="cyber-main">
      <router-view v-slot="{ Component }">
        <transition name="page-transition" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </v-main>

    <!-- グローバルスナックバー (Pinia の ui ストアで制御) -->
    <v-snackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      :timeout="snackbar.timeout"
      location="bottom end"
      class="glass-snackbar"
    >
      <div class="d-flex align-center">
        <v-icon
          :icon="snackbar.color === 'error' ? 'mdi-alert-circle' : 'mdi-check-circle'"
          class="mr-2"
          size="20"
        />
        <span>{{ snackbar.message }}</span>
      </div>
      <template #actions>
        <v-btn icon="mdi-close" variant="text" size="small" @click="snackbar.show = false" />
      </template>
    </v-snackbar>
  </v-app>
</template>

<script setup>
/**
 * App.vue - アプリケーションルート
 * グローバルナビゲーション、背景デザイン、スナックバー通知を一括管理
 */
import { onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useUiStore } from '@/stores/ui'
import logoUrl from '@/assets/logo.jpg'

const uiStore = useUiStore()
const { snackbar, sidebarOpen } = storeToRefs(uiStore)

// キーボードショートカット (Ctrl+B / Cmd+B) によるサイドバー開閉トグル
function handleKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
    // 入力フォームにフォーカス中はスキップ
    const activeEl = document.activeElement
    if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA')) {
      return
    }
    e.preventDefault()
    uiStore.toggleSidebar()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<style>
/* ─── グローバルデザインシステムトークン ─── */
:root {
  --button-gap: 4px;
  --border-radius: 6px;
}

/* ─── グローバルタイポグラフィ & ルート設定 ─── */
html, body {
  margin: 0;
  padding: 0;
  font-family: 'Plus Jakarta Sans', 'Noto Sans JP', -apple-system, BlinkMacSystemFont, sans-serif !important;
  color: #e2e8f0;
  background-color: #090a14 !important;
  overflow-x: hidden;
}

#app {
  min-height: 100vh;
  background: #090a14 !important;
  background-image: 
    radial-gradient(at 10% 10%, rgba(6, 182, 212, 0.12) 0px, transparent 45%),
    radial-gradient(at 90% 15%, rgba(168, 85, 247, 0.14) 0px, transparent 50%),
    radial-gradient(at 50% 95%, rgba(99, 102, 241, 0.10) 0px, transparent 50%),
    radial-gradient(at 50% 50%, rgba(15, 23, 42, 0.6) 0px, transparent 100%) !important;
  background-attachment: fixed !important;
}

.v-application {
  background: transparent !important;
  font-family: inherit !important;
}
.v-main {
  background: transparent !important;
}

/* ─── スタイリッシュな細身のネオンスクロールバー ─── */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: rgba(9, 10, 20, 0.6);
}
::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 999px;
  transition: background 0.2s ease;
}
::-webkit-scrollbar-thumb:hover {
  background: rgba(6, 182, 212, 0.5);
  box-shadow: 0 0 8px rgba(6, 182, 212, 0.4);
}

/* ─── テキスト選択ハイライト ─── */
::selection {
  background: rgba(6, 182, 212, 0.35);
  color: #ffffff;
}

/* ─── グラスモーフィズム共通定義 (Cyber Studio Glass) ─── */
/* 角丸の一律統一 (border-radius: 6px) */
.v-card,
.v-sheet,
.v-expansion-panel,
.glass-card,
.glass-panel,
.rounded,
.rounded-lg,
.rounded-xl,
.rounded-xxl {
  border-radius: 6px !important;
}

.v-btn:not(.v-btn--icon) {
  border-radius: 6px !important;
}

.v-field,
.v-field__outline {
  border-radius: 6px !important;
}

.glass-card {
  background: rgba(19, 22, 40, 0.55) !important;
  backdrop-filter: blur(20px) saturate(180%) !important;
  -webkit-backdrop-filter: blur(20px) saturate(180%) !important;
  border: 1px solid rgba(255, 255, 255, 0.07) !important;
  box-shadow: 
    0 8px 32px 0 rgba(0, 0, 0, 0.45),
    inset 0 1px 0 0 rgba(255, 255, 255, 0.12) !important;
  border-radius: 6px !important;
}

/* ホバー可能なインタラクティブ・グラスカード */
.glass-card-interactive {
  transition: all 0.28s cubic-bezier(0.16, 1, 0.3, 1) !important;
  cursor: pointer;
}
.glass-card-interactive:hover {
  background: rgba(25, 30, 54, 0.75) !important;
  border-color: rgba(6, 182, 212, 0.4) !important;
  box-shadow: 
    0 16px 40px -8px rgba(0, 0, 0, 0.6),
    0 0 24px 0 rgba(6, 182, 212, 0.2),
    inset 0 1px 0 0 rgba(255, 255, 255, 0.2) !important;
  transform: translateY(-3px);
}

/* グラスサイドバー */
.glass-sidebar {
  background: rgba(12, 14, 26, 0.65) !important;
  backdrop-filter: blur(24px) !important;
  -webkit-backdrop-filter: blur(24px) !important;
  border-right: 1px solid rgba(255, 255, 255, 0.06) !important;
  box-shadow: 4px 0 24px 0 rgba(0, 0, 0, 0.4) !important;
}

/* サイドバー折りたたみボタン (ヘッダー内) */
.sidebar-toggle-btn {
  color: rgba(255, 255, 255, 0.6) !important;
  transition: all 0.2s ease !important;
  border-radius: 6px !important;
}
.sidebar-toggle-btn:hover {
  color: #22d3ee !important;
  background: rgba(6, 182, 212, 0.15) !important;
}

/* サイドバー展開用エッジトグルタブ (サイドバー非表示時に画面左端で常時アクセス可能) */
.sidebar-edge-tab {
  position: fixed;
  left: 0;
  top: 72px;
  z-index: 1005;
  width: 24px;
  height: 52px;
  background: rgba(15, 23, 42, 0.9);
  border: 1px solid rgba(6, 182, 212, 0.45);
  border-left: none;
  border-radius: 0 6px 6px 0;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  color: #06b6d4;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 2px 0 16px rgba(0, 0, 0, 0.5), 0 0 10px rgba(6, 182, 212, 0.2);
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.sidebar-edge-tab:hover {
  width: 32px;
  background: rgba(6, 182, 212, 0.25);
  color: #ffffff;
  box-shadow: 3px 0 20px rgba(6, 182, 212, 0.5);
}

/* フェードトランジション */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* グラスパネル (ツールバー・サブヘッダー用) */
.glass-panel {
  background: rgba(18, 21, 38, 0.65) !important;
  backdrop-filter: blur(16px) !important;
  -webkit-backdrop-filter: blur(16px) !important;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
}

/* グラスダイアログ */
.v-dialog > .v-overlay__content > .v-card {
  background: rgba(18, 22, 40, 0.85) !important;
  backdrop-filter: blur(28px) saturate(190%) !important;
  -webkit-backdrop-filter: blur(28px) saturate(190%) !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  box-shadow: 
    0 24px 64px 0 rgba(0, 0, 0, 0.7),
    0 0 32px 0 rgba(6, 182, 212, 0.15),
    inset 0 1px 0 0 rgba(255, 255, 255, 0.2) !important;
  border-radius: 6px !important;
}

/* ナビゲーションアイテムのアクティブ状態 */
.nav-item {
  border-radius: 6px !important;
  transition: all 0.2s ease !important;
  color: rgba(255, 255, 255, 0.7) !important;
  position: relative;
}
.nav-item:hover {
  background: rgba(255, 255, 255, 0.05) !important;
  color: #ffffff !important;
}
.nav-item-active {
  background: linear-gradient(90deg, rgba(6, 182, 212, 0.15) 0%, rgba(168, 85, 247, 0.05) 100%) !important;
  color: #22d3ee !important;
  border: 1px solid rgba(6, 182, 212, 0.3) !important;
  font-weight: 600 !important;
}
.nav-item-active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 15%;
  bottom: 15%;
  width: 3px;
  background: #06b6d4;
  border-radius: 0 4px 4px 0;
  box-shadow: 0 0 10px #06b6d4;
}

/* サイドバーステータスバッジ */
.glass-status-badge {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
}
.status-indicator-live {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background-color: #10b981;
  box-shadow: 0 0 8px #10b981;
  animation: pulse-green 2s infinite;
}
@keyframes pulse-green {
  0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
  70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
  100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
}

.pulse-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: #06b6d4;
  box-shadow: 0 0 6px #06b6d4;
}

/* ─── 汎用ユーティリティクラス ─── */
.text-xxs {
  font-size: 0.7rem !important;
  line-height: 1rem !important;
}
.text-cyan {
  color: #06b6d4 !important;
}
.text-purple {
  color: #c084fc !important;
}
.font-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important;
}

/* ページ遷移アニメーション */
.page-transition-enter-active,
.page-transition-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.page-transition-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.page-transition-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* ロゴヘッダー */
.logo-header {
  position: relative;
}
.logo-avatar-wrapper {
  position: relative;
  width: 40px;
  height: 40px;
}
.logo-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 4px 16px rgba(6, 182, 212, 0.4);
  position: relative;
  z-index: 2;
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.logo-avatar-wrapper:hover .logo-img {
  transform: scale(1.08) rotate(3deg);
}
.logo-glow {
  position: absolute;
  top: -4px;
  left: -4px;
  right: -4px;
  bottom: -4px;
  background: linear-gradient(135deg, rgba(6, 182, 212, 0.6), rgba(168, 85, 247, 0.6));
  border-radius: 6px;
  filter: blur(8px);
  opacity: 0.7;
  z-index: 1;
}
.logo-title {
  background: linear-gradient(135deg, #ffffff 20%, #22d3ee 70%, #c084fc 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: 0.5px;
}
</style>
