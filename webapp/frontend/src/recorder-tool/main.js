/**
 * ローカル録音ツール（#12）のエントリポイント
 *
 * HTTP で運用していてブラウザのマイクを使えない環境向けに、
 * ダウンロードした HTML をブラウザで直接開いて（file://）録音するためのツール。
 */
import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

createApp(App).mount('#app')
