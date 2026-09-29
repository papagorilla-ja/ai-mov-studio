<template>
  <div ref="toolbarRoot" class="narration-toolbar d-flex align-center justify-space-between flex-wrap gap-2 mb-2 px-1">
    <!-- ─── 左側: 操作ツールボタン群 ─── -->
    <div class="d-flex align-center toolbar-actions">
      <!-- 🔤 読みを指定 ボタン -->
      <v-btn
        id="btn-specify-reading"
        size="small"
        variant="tonal"
        color="cyan"
        class="font-weight-bold"
        prepend-icon="mdi-format-letter-case"
        :disabled="!hasSelectedText || !sceneId"
        :loading="guessing"
        @mousedown="onSpecifyReadingMouseDown"
        @click="openSpecifyReadingDialog"
      >
        読みを指定
      </v-btn>

      <!-- ⏸ 間を入れる ▾ メニュー -->
      <v-menu v-model="pauseMenu" :close-on-content-click="false" location="bottom start">
        <template #activator="{ props: menuProps }">
          <v-btn
            id="btn-insert-pause"
            v-bind="menuProps"
            size="small"
            variant="tonal"
            color="purple-lighten-2"
            class="font-weight-bold"
            prepend-icon="mdi-pause-circle-outline"
            append-icon="mdi-menu-down"
            :disabled="!sceneId"
            @mousedown="onPauseButtonMouseDown"
          >
            間を入れる
          </v-btn>
        </template>

        <v-list density="compact" class="glass-card pa-1" elevation="8" min-width="190">
          <v-list-item
            class="rounded-md"
            prepend-icon="mdi-timer-sand-empty"
            @click="insertPause('short')"
          >
            <v-list-item-title class="text-caption font-weight-bold">短い (0.3秒)</v-list-item-title>
            <v-list-item-subtitle class="text-xxs font-mono text-medium-emphasis">［間:0.3］</v-list-item-subtitle>
          </v-list-item>

          <v-list-item
            class="rounded-md"
            prepend-icon="mdi-timer-sand"
            @click="insertPause('normal')"
          >
            <v-list-item-title class="text-caption font-weight-bold">ふつう (0.5秒)</v-list-item-title>
            <v-list-item-subtitle class="text-xxs font-mono text-medium-emphasis">［間］</v-list-item-subtitle>
          </v-list-item>

          <v-list-item
            class="rounded-md"
            prepend-icon="mdi-timer-sand-full"
            @click="insertPause('long')"
          >
            <v-list-item-title class="text-caption font-weight-bold">長い (1.0秒)</v-list-item-title>
            <v-list-item-subtitle class="text-xxs font-mono text-medium-emphasis">［間:1］</v-list-item-subtitle>
          </v-list-item>

          <v-divider class="my-1 border-opacity-10" />

          <v-list-item
            class="rounded-md"
            prepend-icon="mdi-clock-edit-outline"
            @click="openCustomPauseDialog"
          >
            <v-list-item-title class="text-caption font-weight-bold">秒数を指定…</v-list-item-title>
            <v-list-item-subtitle class="text-xxs text-medium-emphasis">0.1〜5.0 秒</v-list-item-subtitle>
          </v-list-item>
        </v-list>
      </v-menu>
    </div>

    <!-- ─── 右側: 選択中の語の簡易表示（選択時のみ） ─── -->
    <div v-if="selectedTextClean" class="d-flex align-center gap-1 text-xxs text-medium-emphasis">
      <span>選択中:</span>
      <code class="text-cyan px-1 py-0.5 rounded bg-black-30 font-weight-bold font-mono">
        {{ selectedTextClean.length > 15 ? selectedTextClean.slice(0, 15) + '…' : selectedTextClean }}
      </code>
    </div>

    <!-- ─── 読みを指定モーダル ─── -->
    <v-dialog v-model="specifyDialog" max-width="460" persistent>
      <v-card class="glass-card pa-2">
        <v-card-title class="d-flex align-center gap-2 text-subtitle-1 font-weight-bold">
          <v-icon color="#06b6d4" size="20">mdi-format-letter-case</v-icon>
          <span>読みを指定</span>
        </v-card-title>

        <v-card-text class="pt-2">
          <p class="text-caption text-medium-emphasis mb-3">
            選択した単語の読みを辞書に登録します。本文に記号（ルビ）は入りません。
          </p>

          <v-alert
            v-if="specifyError"
            type="error"
            variant="tonal"
            density="compact"
            class="mb-3 text-caption"
            closable
            @click:close="specifyError = ''"
          >
            {{ specifyError }}
          </v-alert>

          <!-- 409重複時の上書き確認アラート -->
          <v-alert
            v-if="existingEntryForOverwrite"
            type="warning"
            variant="tonal"
            density="compact"
            class="mb-3 text-caption"
          >
            「{{ readingForm.surface }}」は既に登録されています。読みを「{{ readingForm.reading }}」に上書きしますか？
          </v-alert>

          <!-- 推定読みのヒント案内 -->
          <v-alert
            v-if="guessSource === 'guess'"
            type="info"
            variant="tonal"
            density="compact"
            class="mb-3 text-caption"
            icon="mdi-information-outline"
          >
            AI・辞書未登録のため推定された読みです。確かめてから登録してください。
          </v-alert>
          <v-alert
            v-else-if="guessSource && guessSource !== 'guess'"
            type="success"
            variant="tonal"
            density="compact"
            class="mb-3 text-caption"
            icon="mdi-check-circle-outline"
          >
            {{ sourceDescription(guessSource) }}に登録されている読みです。
          </v-alert>

          <!-- 表記入力欄 -->
          <v-text-field
            v-model="readingForm.surface"
            label="表記"
            density="comfortable"
            class="mb-3"
            hint="50文字以内。記号 ｜《》［］ は使用できません"
            persistent-hint
            :rules="[v => !!v?.trim() || '表記を入力してください', v => !MARKUP_CHARS.test(v || '') || '記号は使えません']"
          />

          <!-- 読み入力欄 -->
          <v-text-field
            v-model="readingForm.reading"
            label="読み（ひらがな・カタカナ等）"
            placeholder="例: けんじゃのいし"
            density="comfortable"
            class="mb-3"
            hint="100文字以内。記号 ｜《》［］ は使用できません"
            persistent-hint
            :rules="[v => !!v?.trim() || '読みを入力してください', v => !MARKUP_CHARS.test(v || '') || '記号は使えません']"
            autofocus
          />

          <!-- 保存先の選択 -->
          <div class="text-caption font-weight-bold mb-1 mt-2">保存先</div>
          <v-radio-group v-model="targetScope" density="compact" hide-details class="mb-2">
            <v-radio value="scene" color="primary">
              <template #label>
                <div class="text-caption">
                  <span class="font-weight-bold">このシーンだけ（既定）</span>
                  <span class="text-medium-emphasis ml-1">— このシーンのみで有効</span>
                </div>
              </template>
            </v-radio>
            <v-radio v-if="projectId" value="project" color="success">
              <template #label>
                <div class="text-caption">
                  <span class="font-weight-bold">このプロジェクト</span>
                  <span class="text-medium-emphasis ml-1">— プロジェクト内すべての動画で有効</span>
                </div>
              </template>
            </v-radio>
            <v-radio value="global" color="purple">
              <template #label>
                <div class="text-caption">
                  <span class="font-weight-bold">すべての動画</span>
                  <span class="text-medium-emphasis ml-1">— システム全体で有効</span>
                </div>
              </template>
            </v-radio>
          </v-radio-group>
        </v-card-text>

        <v-card-actions class="px-4 pb-3 justify-end gap-2">
          <v-btn variant="text" :disabled="saving" @click="closeSpecifyDialog">
            キャンセル
          </v-btn>
          <v-btn
            v-if="existingEntryForOverwrite"
            color="warning"
            variant="flat"
            :loading="saving"
            @click="submitOverwrite"
          >
            上書きする
          </v-btn>
          <v-btn
            v-else
            color="primary"
            variant="flat"
            :loading="saving"
            :disabled="!isReadingFormValid"
            @click="submitSpecifyReading"
          >
            登録する
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ─── 秒数指定モーダル ─── -->
    <v-dialog v-model="customPauseDialog" max-width="360" persistent>
      <v-card class="glass-card pa-2">
        <v-card-title class="d-flex align-center gap-2 text-subtitle-1 font-weight-bold">
          <v-icon color="purple-lighten-2" size="20">mdi-clock-edit-outline</v-icon>
          <span>間の秒数を指定</span>
        </v-card-title>
        <v-card-text class="pt-2">
          <p class="text-caption text-medium-emphasis mb-3">
            0.1 〜 5.0 秒の範囲で間の長さを指定してください。
          </p>

          <v-text-field
            v-model.number="customPauseSec"
            type="number"
            step="0.1"
            min="0.1"
            max="5.0"
            label="秒数 (秒)"
            suffix="秒"
            density="comfortable"
            hint="上限 5.0 秒"
            persistent-hint
            autofocus
            :rules="[
              v => v !== null && v !== undefined && v !== '' || '入力してください',
              v => v >= 0.1 && v <= 5.0 || '0.1 〜 5.0 秒で入力してください'
            ]"
            class="mb-2"
          />

          <div class="pa-2 rounded bg-black-20 text-caption font-mono mt-2">
            挿入書式: <span class="text-purple-lighten-2 font-weight-bold">［間:{{ customPauseSec || 1.5 }}］</span>
          </div>
        </v-card-text>
        <v-card-actions class="px-4 pb-3 justify-end gap-2">
          <v-btn variant="text" @click="customPauseDialog = false">キャンセル</v-btn>
          <v-btn
            color="purple-lighten-2"
            variant="flat"
            :disabled="!isCustomPauseValid"
            @click="confirmCustomPause"
          >
            挿入
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { readingApi } from '@/api/reading'
import { useUiStore } from '@/stores/ui'

const props = defineProps({
  sceneId: {
    type: String,
    required: true,
  },
  projectId: {
    type: String,
    default: null,
  },
  modelValue: {
    type: String,
    default: '',
  },
  textareaEl: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['update:modelValue', 'reading-registered'])

const ui = useUiStore()

const MARKUP_CHARS = /[｜|《》［］[\]\n]/

// 選択状態
const rawSelectedText = ref('')
const savedSelection = ref({ start: 0, end: 0 })

// 記号を取り除いた選択文字
const selectedTextClean = computed(() => {
  if (!rawSelectedText.value) return ''
  // 記号を外したプレーンな文字
  const t = rawSelectedText.value
    .replace(/[｜|]([^｜|《》\n]+?)《([^《》\n]+?)》/g, '$1')
    .replace(/[［\[]間(?:\s*[:：]\s*\d+(?:\.\d+)?)?\s*[］\]]/g, '')
    .trim()
  return t
})

const hasSelectedText = computed(() => {
  return Boolean(selectedTextClean.value && selectedTextClean.value.length > 0)
})

// 読み指定ダイアログ
const specifyDialog = ref(false)
const guessing = ref(false)
const saving = ref(false)
const specifyError = ref('')
const guessSource = ref('')
const targetScope = ref('scene')
const existingEntryForOverwrite = ref(null)

const readingForm = ref({
  surface: '',
  reading: '',
})

// 間を入れるメニュー・カスタム秒数ダイアログ
const pauseMenu = ref(false)
const customPauseDialog = ref(false)
const customPauseSec = ref(1.5)

const isReadingFormValid = computed(() => {
  const s = readingForm.value.surface?.trim()
  const r = readingForm.value.reading?.trim()
  if (!s || !r) return false
  if (s.length > 50 || r.length > 100) return false
  if (MARKUP_CHARS.test(s) || MARKUP_CHARS.test(r)) return false
  return true
})

const isCustomPauseValid = computed(() => {
  const v = customPauseSec.value
  return typeof v === 'number' && !isNaN(v) && v >= 0.1 && v <= 5.0
})

function sourceDescription(src) {
  switch (src) {
    case 'scene': return 'このシーン'
    case 'project': return 'プロジェクト辞書'
    case 'global': return '全体辞書'
    case 'ai': return 'AI自動仮名化'
    default: return '辞書'
  }
}

const toolbarRoot = ref(null)

function getTargetTextarea() {
  if (props.textareaEl) return props.textareaEl
  if (toolbarRoot.value) {
    const parent = toolbarRoot.value.closest('.v-expansion-panel-text') || toolbarRoot.value.parentElement
    if (parent) {
      const ta = parent.querySelector('textarea')
      if (ta) return ta
    }
  }
  return typeof document !== 'undefined'
    ? (document.querySelector('.v-expansion-panel[value="narration"] textarea') || document.querySelector('textarea'))
    : null
}

// テキストエリアの選択範囲の更新
function handleSelectionChange(sourceEvent) {
  const el = getTargetTextarea()
  if (!el) return
  const start = el.selectionStart ?? 0
  const end = el.selectionEnd ?? 0
  if (start !== end) {
    savedSelection.value = { start, end }
    const text = el.value ?? props.modelValue ?? ''
    rawSelectedText.value = text.slice(start, end)
  } else {
    // 選択が解除された場合（ただしツールバー内をクリックした時はボタン操作のため維持する）
    if (sourceEvent?.target && toolbarRoot.value?.contains(sourceEvent.target)) {
      return
    }
    savedSelection.value = { start, end }
    rawSelectedText.value = ''
  }
}

// 読みを指定ダイアログを開く
async function openSpecifyReadingDialog() {
  if (!hasSelectedText.value || !props.sceneId) return
  guessing.value = true
  specifyError.value = ''
  existingEntryForOverwrite.value = null
  targetScope.value = 'scene'

  const surface = selectedTextClean.value
  readingForm.value = {
    surface,
    reading: '',
  }

  try {
    const res = await readingApi.guessSceneReading(props.sceneId, surface)
    readingForm.value.surface = res.data.surface || surface
    readingForm.value.reading = res.data.reading || ''
    guessSource.value = res.data.source || 'guess'
    specifyDialog.value = true
  } catch (e) {
    const msg = e.message || '読みの推定に失敗しました'
    specifyError.value = msg
    guessSource.value = 'guess'
    // 推定に失敗してもダイアログは開いて手入力可能にする
    specifyDialog.value = true
  } finally {
    guessing.value = false
  }
}

function closeSpecifyDialog() {
  specifyDialog.value = false
  specifyError.value = ''
  existingEntryForOverwrite.value = null
}

async function findExisting(scope, surface) {
  try {
    let listRes
    if (scope === 'scene') {
      listRes = await readingApi.listScene(props.sceneId)
    } else if (scope === 'project') {
      if (!props.projectId) return null
      listRes = await readingApi.listProject(props.projectId)
    } else {
      listRes = await readingApi.listGlobal()
    }
    return (listRes.data || []).find(e => e.surface === surface) || null
  } catch {
    return null
  }
}

// 読みを登録
async function submitSpecifyReading() {
  if (!isReadingFormValid.value) return
  saving.value = true
  specifyError.value = ''
  existingEntryForOverwrite.value = null

  const payload = {
    surface: readingForm.value.surface.trim(),
    reading: readingForm.value.reading.trim(),
  }

  try {
    if (targetScope.value === 'scene') {
      await readingApi.createScene(props.sceneId, payload)
      ui.notify(`「${payload.surface}」をこのシーンの読みに登録しました`)
    } else if (targetScope.value === 'project') {
      if (!props.projectId) throw new Error('プロジェクトIDがありません')
      await readingApi.createProject(props.projectId, payload)
      ui.notify(`「${payload.surface}」をプロジェクト辞書に登録しました`)
    } else {
      await readingApi.createGlobal(payload)
      ui.notify(`「${payload.surface}」を全体辞書に登録しました`)
    }

    closeSpecifyDialog()
    emit('reading-registered')
  } catch (e) {
    const msg = e.message || '登録に失敗しました'
    specifyError.value = msg
    if (msg.includes('すでにこの辞書にあります') || e.response?.status === 409) {
      const existing = await findExisting(targetScope.value, payload.surface)
      if (existing) {
        existingEntryForOverwrite.value = existing
      }
    }
    ui.notifyError(msg)
  } finally {
    saving.value = false
  }
}

// 上書き実行
async function submitOverwrite() {
  if (!existingEntryForOverwrite.value) return
  saving.value = true
  specifyError.value = ''

  const payload = {
    surface: readingForm.value.surface.trim(),
    reading: readingForm.value.reading.trim(),
  }

  try {
    await readingApi.updateEntry(existingEntryForOverwrite.value.id, payload)
    ui.notify(`「${payload.surface}」の読みを上書き更新しました`)
    closeSpecifyDialog()
    emit('reading-registered')
  } catch (e) {
    const msg = e.message || '上書きに失敗しました'
    specifyError.value = msg
    ui.notifyError(msg)
  } finally {
    saving.value = false
  }
}

// 読みボタン・間ボタンの mousedown 時に最新位置を保存
function onSpecifyReadingMouseDown() {
  const el = getTargetTextarea()
  if (el) {
    const start = el.selectionStart ?? 0
    const end = el.selectionEnd ?? 0
    savedSelection.value = { start, end }
    if (start !== end) {
      const text = el.value ?? props.modelValue ?? ''
      rawSelectedText.value = text.slice(start, end)
    }
  }
}

function onPauseButtonMouseDown() {
  const el = getTargetTextarea()
  if (el) {
    savedSelection.value = {
      start: el.selectionStart ?? 0,
      end: el.selectionEnd ?? 0,
    }
  }
}

// 間の挿入
function insertPause(type) {
  pauseMenu.value = false
  let pauseMarkup = ''
  switch (type) {
    case 'short':
      pauseMarkup = '［間:0.3］'
      break
    case 'normal':
      pauseMarkup = '［間］'
      break
    case 'long':
      pauseMarkup = '［間:1］'
      break
    default:
      pauseMarkup = '［間］'
  }
  executeInsert(pauseMarkup)
}

function openCustomPauseDialog() {
  pauseMenu.value = false
  customPauseDialog.value = true
}

function confirmCustomPause() {
  if (!isCustomPauseValid.value) return
  const sec = Number(customPauseSec.value)
  const pauseMarkup = `［間:${sec}］`
  customPauseDialog.value = false
  executeInsert(pauseMarkup)
}

// 共通挿入処理
function executeInsert(insertStr) {
  const el = getTargetTextarea()
  const cur = el?.value ?? props.modelValue ?? ''
  const start = savedSelection.value.start
  const end = savedSelection.value.end

  const newText = cur.slice(0, start) + insertStr + cur.slice(end)
  emit('update:modelValue', newText)

  // 挿入後、カーソルを間の後ろに移動してフォーカスを戻す
  nextTick(() => {
    const targetEl = getTargetTextarea()
    if (targetEl) {
      const newPos = start + insertStr.length
      targetEl.focus()
      targetEl.setSelectionRange(newPos, newPos)
      savedSelection.value = { start: newPos, end: newPos }
      rawSelectedText.value = ''
    }
  })
}

// selectionchange リスナー（textarea がフォーカスされている間リアルタイム追従）
function onDocSelectionChange(e) {
  const el = getTargetTextarea()
  if (el && (document.activeElement === el || document.activeElement?.contains?.(el))) {
    handleSelectionChange(e)
  }
}

// グローバル mouseup/keyup リスナー（マウスドラッグ選択やキーボード選択の終了を確実に検知）
function onGlobalSelection(e) {
  if (specifyDialog.value || customPauseDialog.value) return
  if (e?.target && toolbarRoot.value?.contains(e.target)) return
  handleSelectionChange(e)
}

function attachEvents(el) {
  if (!el) return
  el.addEventListener('select', handleSelectionChange)
  el.addEventListener('mouseup', handleSelectionChange)
  el.addEventListener('keyup', handleSelectionChange)
  el.addEventListener('focus', handleSelectionChange)
}

function detachEvents(el) {
  if (!el) return
  el.removeEventListener('select', handleSelectionChange)
  el.removeEventListener('mouseup', handleSelectionChange)
  el.removeEventListener('keyup', handleSelectionChange)
  el.removeEventListener('focus', handleSelectionChange)
}

watch(() => props.textareaEl, (newEl, oldEl) => {
  detachEvents(oldEl)
  attachEvents(newEl)
}, { immediate: true })

onMounted(() => {
  document.addEventListener('selectionchange', onDocSelectionChange)
  window.addEventListener('mouseup', onGlobalSelection)
  window.addEventListener('keyup', onGlobalSelection)
  nextTick(() => {
    attachEvents(getTargetTextarea())
  })
})

onBeforeUnmount(() => {
  document.removeEventListener('selectionchange', onDocSelectionChange)
  window.removeEventListener('mouseup', onGlobalSelection)
  window.removeEventListener('keyup', onGlobalSelection)
  detachEvents(getTargetTextarea())
})
</script>

<style scoped>
.narration-toolbar {
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  padding-bottom: 6px;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* 汎用 Gap ユーティリティ */
.gap-1 { gap: 4px !important; }
.gap-2 { gap: 8px !important; }
.gap-3 { gap: 12px !important; }

.bg-black-20 {
  background: rgba(0, 0, 0, 0.25);
}
.bg-black-30 {
  background: rgba(0, 0, 0, 0.35);
}
</style>
