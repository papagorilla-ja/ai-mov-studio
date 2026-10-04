<template>
  <div class="page">
    <header class="page-header">
      <h1 class="page-title">🎙 話者の音声 録音ツール</h1>
      <p class="page-subtitle">AI Mov-Studio の話者（声質クローン）に使う音声を、このパソコンで録音します。</p>
    </header>

    <main class="card">
      <SetupStep
        v-if="step === 'setup'"
        :modes="availableModes"
        :problem="problem"
        @start="startSession"
      />
      <RecordStep
        v-else-if="step === 'record'"
        v-model:index="session.index"
        :items="session.items"
        :takes="session.takes"
        :mode-label="recordingModeLabel(session.mode)"
        @save-take="saveTake"
        @finish="step = 'save'"
        @restart="restart"
      />
      <SaveStep
        v-else
        :items="session.items"
        :takes="session.takes"
        :mode="session.mode"
        :app-url="data?.app_url || ''"
        :saved-file-name="savedFileName"
        @saved="savedFileName = $event"
        @back="step = 'record'"
        @restart="restart"
      />
    </main>

    <footer class="page-footer">
      録音した音声は、このパソコンの中だけで処理されます（インターネットには送信されません）。
    </footer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { isMicrophoneSupported } from '@/audio/capture.js'
import { RECORDING_MODES, recordingModeLabel } from '@/constants/recordingModes.js'
import { readRecorderData } from './embeddedData.js'
import RecordStep from './components/RecordStep.vue'
import SaveStep from './components/SaveStep.vue'
import SetupStep from './components/SetupStep.vue'

// 設定画面からダウンロードしたときに埋め込まれたデータ（読み上げ文など）
const data = readRecorderData()

// 録音を始められない理由。'no-data': データが無い / 'no-mic': マイクを使えないブラウザ
const problem = data ? (isMicrophoneSupported() ? null : 'no-mic') : 'no-data'

// 埋め込まれた項目があるモードだけを選べるようにする
const availableModes = RECORDING_MODES.filter(m => data?.items?.[m.value]?.length > 0)

/** @type {import('vue').Ref<'setup'|'record'|'save'>} */
const step = ref('setup')
const session = reactive({
  mode: '',
  items: [],   // 提示項目 [{ index, prompt, instruction, kind }]
  takes: [],   // 項目と同じ順のテイク（未録音は null）
  index: 0,    // 収録中の項目の番号（0 始まり）
})
// 保存した収録データのファイル名（未保存なら空）
const savedFileName = ref('')

function startSession({ mode, count }) {
  const items = data.items[mode].slice(0, count)
  session.mode = mode
  session.items = items
  session.takes = items.map(() => null)
  session.index = 0
  savedFileName.value = ''
  step.value = 'record'
}

function saveTake(index, saved) {
  session.takes[index] = saved
  // 録り直したら、保存済みの収録データとは中身が変わる
  savedFileName.value = ''
}

const hasUnsavedTakes = computed(() => session.takes.some(Boolean) && !savedFileName.value)

function restart() {
  if (hasUnsavedTakes.value && !confirm('保存していない録音があります。破棄して最初からやり直しますか？')) return
  session.takes = []
  savedFileName.value = ''
  step.value = 'setup'
}

// 保存していない録音があるのにタブを閉じようとしたら確認する。
// 収録の手順にいる間は、表示中の項目に「次へ」を押す前の録音があり得るので常に確認する
function confirmLeave(e) {
  if (step.value !== 'record' && !hasUnsavedTakes.value) return
  e.preventDefault()
  e.returnValue = ''
}
window.addEventListener('beforeunload', confirmLeave)
onBeforeUnmount(() => window.removeEventListener('beforeunload', confirmLeave))
</script>
