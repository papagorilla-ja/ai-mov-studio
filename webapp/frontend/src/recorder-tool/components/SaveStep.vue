<template>
  <section>
    <p class="lead center">🎉 収録が完了しました（{{ takes.length }}本）。</p>

    <!-- 録音したテイクの一覧 -->
    <table class="take-table">
      <thead>
        <tr><th>#</th><th>内容</th><th>長さ</th><th>ノイズ除去</th><th>注意</th></tr>
      </thead>
      <tbody>
        <tr v-for="(saved, i) in takes" :key="i">
          <td>{{ i + 1 }}</td>
          <td class="take-prompt">{{ items[i].prompt }}</td>
          <td>{{ saved.take.durationSec.toFixed(1) }}秒</td>
          <td>{{ noiseReductionLabel(saved.noiseReduction) }}</td>
          <td>
            <span v-if="saved.take.analysis.warnings.length" class="warning-mark" :title="warningText(saved)">⚠ {{ saved.take.analysis.warnings.length }}</span>
            <span v-else class="ok-mark">OK</span>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="warningCount > 0" class="hint">
      注意のあるテイクが {{ warningCount }} 本あります（⚠ にマウスを重ねると内容が出ます）。「戻って録り直す」から録り直せます。
    </p>

    <label class="field-label" for="recording-name">収録音声の名前</label>
    <input
      id="recording-name"
      v-model="name"
      class="input"
      type="text"
      :maxlength="MAX_NAME_LENGTH"
      placeholder="例: 山田さんの声（落ち着いたトーン）"
    />
    <p class="hint">取り込むと、この名前で AI Mov-Studio の「収録音声ライブラリ」に登録されます（取り込むときに変更もできます）。</p>

    <div v-if="error" class="alert alert-error">{{ error }}</div>

    <!-- 保存後の案内 -->
    <div v-if="savedFileName" class="alert alert-success">
      <div class="alert-title">保存しました: {{ savedFileName }}</div>
      AI Mov-Studio の「設定」→「話者管理」→「収録データを取り込む」から、このファイルを選んでください。
      <div v-if="appUrl" class="mt">
        <a :href="appUrl" target="_blank" rel="noopener">AI Mov-Studio の設定画面を開く</a>
      </div>
    </div>

    <div class="actions between">
      <div class="actions">
        <button type="button" class="btn btn-outline" @click="emit('back')">← 戻って録り直す</button>
        <button type="button" class="btn btn-text" @click="emit('restart')">新しく収録する</button>
      </div>
      <button type="button" class="btn btn-primary" :disabled="!name.trim()" @click="save">
        {{ savedFileName ? 'もう一度保存する' : '収録データを保存する（.zip）' }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { findNoiseReductionLevel } from '@/audio/config.js'
import { saveBlobAsFile } from '@/utils/download.js'
import { buildRecordingPackage, packageFileName } from '../recordingPackage.js'

// サーバー側（services/recording_package.py の MAX_NAME_LENGTH）と同じ上限
const MAX_NAME_LENGTH = 100

const props = defineProps({
  items: { type: Array, required: true },
  // 項目と同じ順のテイク（すべて録音済み）
  takes: { type: Array, required: true },
  mode: { type: String, required: true },
  // AI Mov-Studio の設定画面の URL（ダウンロード時に埋め込まれる）
  appUrl: { type: String, default: '' },
  // 保存した収録データのファイル名（未保存なら空）
  savedFileName: { type: String, default: '' },
})
const emit = defineEmits(['saved', 'back', 'restart'])

const name = ref('')
const error = ref('')

const warningCount = computed(() => props.takes.filter(t => t.take.analysis.warnings.length > 0).length)

function noiseReductionLabel(value) {
  return findNoiseReductionLevel(value).label
}

function warningText(saved) {
  return saved.take.analysis.warnings.map(w => w.message).join('\n')
}

function save() {
  error.value = ''
  try {
    const trimmed = name.value.trim()
    const blob = buildRecordingPackage({ name: trimmed, mode: props.mode, items: props.items, takes: props.takes })
    const fileName = packageFileName(trimmed)
    saveBlobAsFile(blob, fileName)
    emit('saved', fileName)
  } catch (e) {
    error.value = `保存に失敗しました: ${e.message}`
  }
}
</script>
