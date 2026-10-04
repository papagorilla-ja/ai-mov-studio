/**
 * ローカル録音ツール（#12）のビルド設定
 *
 * tools/voice-recorder.html を入口に、JS と CSS をすべて HTML に埋め込んだ
 * 1 つのファイル（dist/tools/voice-recorder.html）を作る。
 * 利用者はこのファイルをダウンロードして、ブラウザで直接開く（file://）。
 * file:// のページは別ファイルの JS を読み込めない（安全のためブラウザが拒否する）ため、埋め込みが必須。
 *
 * 本体のビルド（vite.config.js）の後に実行する（npm run build が両方を順に実行する）。
 */
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

const ENTRY_HTML = fileURLToPath(new URL('./tools/voice-recorder.html', import.meta.url))

/** 正規表現の特殊文字を無効にする。 */
const escapeRegExp = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/**
 * 出力された JS・CSS を HTML に埋め込み、別ファイルとしては書き出さないプラグイン。
 * 埋め込めなかったファイルが残ったら、単一 HTML にならないのでビルドを失敗させる。
 */
function inlineIntoHtml() {
  return {
    name: 'voice-recorder-inline-into-html',
    enforce: 'post',
    generateBundle(_options, bundle) {
      const html = Object.values(bundle).find(f => f.type === 'asset' && f.fileName.endsWith('.html'))
      if (!html) this.error('録音ツールの HTML が出力されていません')
      let source = String(html.source)

      for (const [fileName, file] of Object.entries(bundle)) {
        if (file === html) continue
        const name = escapeRegExp(fileName.split('/').pop())
        if (file.type === 'chunk') {
          // HTML の中で "</script" が現れるとそこで script 要素が終わってしまうため、エスケープする
          const code = file.code.replace(/<\/script/gi, '<\\/script')
          const tag = new RegExp(`<script\\b[^>]*\\bsrc="[^"]*${name}"[^>]*></script>`)
          // 置き換え後の文字列に "$" が含まれても特別扱いされないよう、関数で返す
          source = source.replace(tag, () => `<script type="module">${code}</script>`)
        } else if (fileName.endsWith('.css')) {
          const tag = new RegExp(`<link\\b[^>]*\\bhref="[^"]*${name}"[^>]*>`)
          source = source.replace(tag, () => `<style>${String(file.source)}</style>`)
        } else {
          this.error(`HTML に埋め込めないファイルが出力されました: ${fileName}`)
        }
        if (source.includes(fileName.split('/').pop())) {
          this.error(`埋め込み後も HTML が別ファイルを参照しています: ${fileName}`)
        }
        delete bundle[fileName]
      }
      html.source = source
    },
  }
}

export default defineConfig({
  // 埋め込むので配置先のパスには依存しない（サブパス運用でもそのまま使える）
  base: './',
  plugins: [vue(), inlineIntoHtml()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: 'dist',
    // 本体のビルド結果（dist/ 直下）を消さない
    emptyOutDir: false,
    // 画像などもすべて data URI にして埋め込む
    assetsInlineLimit: Number.MAX_SAFE_INTEGER,
    cssCodeSplit: false,
    // modulepreload の補助スクリプトは、埋め込むので不要
    modulePreload: false,
    sourcemap: false,
    rollupOptions: {
      input: ENTRY_HTML,
      // 動的 import があっても 1 つの JS にまとめる
      output: { inlineDynamicImports: true },
    },
  },
})
