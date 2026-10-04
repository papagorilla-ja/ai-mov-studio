<template>
  <section>
    <!-- 進み具合 -->
    <div class="progress-row">
      <span class="progress-label">
        {{ index + 1 }} / {{ items.length }}
        <span class="chip">{{ modeLabel }}</span>
      </span>
      <div class="progress-bar"><div class="progress-fill" :style="{ width: `${progressPercent}%` }"></div></div>
    </div>

    <!-- 提示項目（チャット対話は吹き出し、それ以外はカード） -->
    <div v-if="item.kind === 'answer'" class="prompt-chat">
      <div class="chat-avatar">🤖</div>
      <div class="chat-bubble">{{ item.prompt }}</div>
    </div>
    <div v-else class="prompt-card">{{ item.prompt }}</div>
    <p class="hint center">{{ item.instruction }}</p>

    <!-- マイクとノイズ除去の強さ（録音中は変えられない） -->
    <div class="control-row">
      <label class="control">
        <span class="field-label">マイク</span>
        <select v-model="recorder.microphoneId" class="select" :disabled="recorder.isBusy">
          <option value="">既定のマイク</option>
          <option v-for="mic in recorder.microphones" :key="mic.deviceId" :value="mic.deviceId">{{ mic.label }}</option>
        </select>
      </label>
      <div class="control">
        <span class="field-label">ノイズ除去</span>
        <div class="segmented">
          <button
            v-for="level in NOISE_REDUCTION_LEVELS"
            :key="level.value"
            type="button"
            :class="{ active: recorder.noiseReduction === level.value }"
            :disabled="recorder.isBusy"
            @click="recorder.noiseReduction = level.value"
          >
            {{ level.label }}
          </button>
        </div>
      </div>
    </div>

    <!-- 波形（カウントダウン中は残り秒数を重ねて表示する） -->
    <div class="waveform-wrap">
      <canvas ref="canvasRef" width="480" height="90" class="waveform"></canvas>
      <div v-if="recorder.phase === 'countdown'" class="countdown-overlay">{{ recorder.countdownLeft }}</div>
    </div>
    <p class="status" :class="statusClass">{{ statusText }}</p>

    <div class="actions center">
      <button
        v-if="!recorder.isCapturing"
        type="button"
        class="btn btn-record"
        :disabled="recorder.phase === 'processing'"
        @click="startRecording"
      >
        ● {{ recorder.hasTake ? '録り直す' : '録音する' }}
      </button>
      <button v-else type="button" class="btn btn-stop" @click="stopRecording">■ 停止する</button>
    </div>

    <!-- 処理前後の聴き比べ -->
    <div v-if="recorder.hasTake" class="actions center">
      <button type="button" class="btn btn-tonal-primary" @click="togglePlayback('processed')">
        {{ recorder.playing === 'processed' ? '■' : '▶' }} ノイズ除去後
      </button>
      <button type="button" class="btn btn-tonal" @click="togglePlayback('original')">
        {{ recorder.playing === 'original' ? '■' : '▶' }} 元の音
      </button>
    </div>

    <!-- 入力レベルの警告・操作のエラー -->
    <div v-for="warning in recorder.warnings" :key="warning.code" class="alert alert-warning">{{ warning.message }}</div>
    <div v-if="message" class="alert" :class="message.type === 'error' ? 'alert-error' : 'alert-info'">{{ message.text }}</div>

    <div class="actions between">
      <div class="actions">
        <button type="button" class="btn btn-outline" :disabled="index === 0 || recorder.isBusy" @click="goTo(index - 1)">
          ← 前へ
        </button>
        <button type="button" class="btn btn-text" :disabled="recorder.isBusy" @click="emit('restart')">最初からやり直す</button>
      </div>
      <button type="button" class="btn btn-primary" :disabled="!recorder.hasTake || recorder.isBusy" @click="next">
        {{ isLast ? '収録を完了する' : 'この録音を使って次へ →' }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { COUNTDOWN_SEC, NOISE_REDUCTION_LEVELS } from '@/audio/config.js'
import { useVoiceTakeRecorder } from '@/composables/useVoiceTakeRecorder.js'

const props = defineProps({
  items: { type: Array, required: true },
  // 項目と同じ順のテイク（未録音は null）。変更は save-take で親に伝える
  takes: { type: Array, required: true },
  // 収録中の項目の番号（v-model:index）
  index: { type: Number, required: true },
  modeLabel: { type: String, required: true },
})
const emit = defineEmits(['update:index', 'save-take', 'finish', 'restart'])

const canvasRef = ref(null)
// reactive で包むと、テンプレートでもスクリプトでも .value なしで扱える
const recorder = reactive(useVoiceTakeRecorder({ canvasRef }))
// 操作の結果を画面に出す一時的なメッセージ（{ type: 'info' | 'error', text }）
const message = ref(null)

const item = computed(() => props.items[props.index])
const isLast = computed(() => props.index === props.items.length - 1)
const progressPercent = computed(() => (props.takes.filter(Boolean).length / props.items.length) * 100)

const statusText = computed(() => {
  switch (recorder.phase) {
    case 'countdown': return `${recorder.countdownLeft} … 話さずにお待ちください（周囲の音を測っています）`
    case 'recording': return `● 録音中です。話してください… ${recorder.elapsedSec}秒`
    case 'processing': return 'ノイズを除去しています…'
    case 'done': return `録音済み（${recorder.durationSec}秒）。再生して確認し、問題なければ次へ進んでください。`
    default: return `録音ボタンを押すと、${COUNTDOWN_SEC}秒のカウントダウンの後に録音が始まります。`
  }
})
const statusClass = computed(() => ({
  'status-warning': recorder.phase === 'countdown',
  'status-recording': recorder.phase === 'recording',
}))

// 項目に保存済みのテイクがあれば表示する（無ければ待機状態）
function showSavedTake() {
  recorder.restoreTake(props.takes[props.index])
}
onMounted(showSavedTake)
watch(() => props.index, showSavedTake)

async function startRecording() {
  message.value = null
  try {
    await recorder.start()
  } catch (e) {
    message.value = { type: 'error', text: e.message }
  }
}

async function stopRecording() {
  try {
    const result = await recorder.stop()
    if (result === 'cancelled') {
      message.value = { type: 'info', text: 'カウントダウン中に停止したため、録音を取り消しました。' }
    } else if (result === 'empty') {
      message.value = { type: 'error', text: '発話が録音されていません。もう一度録音してください。' }
    }
  } catch (e) {
    message.value = { type: 'error', text: `録音の処理に失敗しました: ${e.message}` }
  }
  // 録り直しが取り消し・失敗に終わったときは、前に保存したテイクを表示し直す
  if (!recorder.hasTake) showSavedTake()
}

function togglePlayback(kind) {
  if (recorder.playing === kind) {
    recorder.stopPlayback()
    return
  }
  recorder.play(kind).catch(e => {
    message.value = { type: 'error', text: `再生に失敗しました: ${e.message}` }
  })
}

// 表示中のテイクを親に預ける（項目を移っても録音が残るように）
function saveCurrentTake() {
  const saved = recorder.exportTake()
  if (saved) emit('save-take', props.index, saved)
}

function goTo(newIndex) {
  saveCurrentTake()
  message.value = null
  emit('update:index', newIndex)
}

function next() {
  if (isLast.value) {
    saveCurrentTake()
    recorder.stopPlayback()
    emit('finish')
  } else {
    goTo(props.index + 1)
  }
}
</script>
