<template>
  <section>
    <!-- 録音を始められないとき（データが無い / マイクを使えないブラウザ） -->
    <div v-if="problem === 'no-data'" class="alert alert-error">
      <div class="alert-title">読み上げ文が見つかりません</div>
      このファイルには、録音で読み上げる文が含まれていません。
      AI Mov-Studio の「設定」画面の「話者管理」から、録音ツールをダウンロードし直してください。
    </div>
    <div v-else-if="problem === 'no-mic'" class="alert alert-error">
      <div class="alert-title">このブラウザではマイクを使えません</div>
      <p>
        {{ isSafari ? 'Safari では、ダウンロードしたファイルからマイクを使えません。' : 'このブラウザでは、ダウンロードしたファイルからマイクを使えません。' }}
        <strong>Google Chrome</strong> または <strong>Microsoft Edge</strong> で、このファイルを開いてください。
      </p>
      <ul class="steps">
        <li><strong>Windows:</strong> ファイルを右クリック →「プログラムから開く」→「Google Chrome」または「Microsoft Edge」</li>
        <li><strong>Mac:</strong> ファイルを右クリック（control＋クリック）→「このアプリケーションで開く」→「Google Chrome」</li>
      </ul>
    </div>

    <template v-else>
      <p class="lead">
        マイクを使って、話者の参照音声を録音します。<br />
        静かな部屋で、マイクから一定の距離（20〜30cm）を保って話してください。
      </p>
      <div class="alert alert-info">
        録音ボタンを押すと <strong>{{ COUNTDOWN_SEC }} 秒のカウントダウン</strong> が始まります。その間は話さずにお待ちください。
        周囲の音を測って、ノイズ除去に使います。ボタンを押したときのクリック音も自動で取り除きます。
      </div>

      <div class="field-label">収録モード</div>
      <div class="radio-list">
        <label v-for="m in modes" :key="m.value" class="radio-item" :class="{ selected: mode === m.value }">
          <input v-model="mode" type="radio" name="mode" :value="m.value" />
          <span>
            <span class="radio-title">{{ m.label }}</span>
            <span class="radio-description">{{ m.description }}</span>
          </span>
        </label>
      </div>

      <label class="field-label" for="item-count">収録する本数</label>
      <select id="item-count" v-model.number="count" class="select">
        <option v-for="n in SESSION_ITEM_COUNTS" :key="n" :value="n">{{ n }} 本</option>
      </select>
      <p class="hint">1 本あたり 5〜20 秒程度。取り込むと、参照音声は自動で約 20 秒に整えられます。</p>

      <div class="actions center">
        <button type="button" class="btn btn-primary btn-large" :disabled="!mode" @click="emit('start', { mode, count })">
          開始する
        </button>
      </div>
    </template>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { COUNTDOWN_SEC } from '@/audio/config.js'
import { DEFAULT_SESSION_ITEM_COUNT, SESSION_ITEM_COUNTS } from '@/constants/recordingModes.js'

const props = defineProps({
  // 選べる収録モード（recordingModes.RECORDING_MODES の要素）
  modes: { type: Array, required: true },
  // 録音を始められない理由（'no-data' / 'no-mic' / null）
  problem: { type: String, default: null },
})
const emit = defineEmits(['start'])

const mode = ref(props.modes[0]?.value ?? '')
const count = ref(DEFAULT_SESSION_ITEM_COUNT)

// Safari は file:// で開いたページからマイクを使えない（Chrome / Edge / Firefox は使える）
const isSafari = /^((?!chrome|chromium|crios|fxios|edg|android).)*safari/i.test(navigator.userAgent)
</script>
