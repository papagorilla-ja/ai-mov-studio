<template>
  <div class="scene-reading-checker mt-3 pt-3 border-t border-opacity-10">
    <!-- ─── ヘッダー部: 状態 & 確認ボタン ─── -->
    <div class="d-flex align-center justify-space-between flex-wrap gap-2 mb-2">
      <div class="d-flex align-center gap-2">
        <v-icon size="18" color="#06b6d4">mdi-text-recognition</v-icon>
        <span class="text-caption font-weight-bold">読みの確認</span>

        <!-- AI確認状態チップ -->
        <template v-if="readingData">
          <v-chip
            v-if="isOutdated"
            size="x-small"
            color="warning"
            variant="tonal"
            prepend-icon="mdi-alert"
          >
            ナレーション変更あり（再確認を推奨）
          </v-chip>
          <v-chip
            v-else-if="readingData.ai_checked"
            size="x-small"
            color="success"
            variant="tonal"
            prepend-icon="mdi-check-circle"
          >
            AI確認済み
          </v-chip>
          <v-chip
            v-else
            size="x-small"
            color="grey"
            variant="tonal"
            prepend-icon="mdi-information-outline"
          >
            未確認（合成時にAIが自動仮名化）
          </v-chip>
        </template>
        <v-chip
          v-else
          size="x-small"
          color="grey"
          variant="tonal"
          prepend-icon="mdi-help-circle-outline"
        >
          未確認
        </v-chip>
      </div>

      <div class="d-flex align-center gap-2">
        <!-- 書式ヒントトグルボタン -->
        <v-btn
          id="btn-reading-hint"
          variant="text"
          size="x-small"
          density="comfortable"
          color="medium-emphasis"
          prepend-icon="mdi-help-circle-outline"
          @click="showFormatHint = !showFormatHint"
        >
          {{ showFormatHint ? 'ヒントを閉じる' : '書式の書き方ヒント' }}
        </v-btn>

        <!-- 「読みを確認」ボタン -->
        <v-btn
          id="btn-check-reading"
          size="small"
          color="cyan"
          variant="tonal"
          class="font-weight-bold"
          prepend-icon="mdi-account-search-outline"
          :loading="loading"
          :disabled="!hasNarrationText"
          @click="runReadingCheck"
        >
          読みを確認
        </v-btn>
      </div>
    </div>

    <!-- ─── 書式の書き方ヒント ─── -->
    <v-expand-transition>
      <div v-if="showFormatHint" class="mb-3">
        <v-card class="pa-3 glass-card bg-opacity-5 rounded-lg border-opacity-10 text-caption">
          <div class="font-weight-bold mb-1 d-flex align-center gap-1 text-cyan">
            <v-icon size="16">mdi-information</v-icon>
            ナレーションの読みと間の指定記法
          </div>
          <div class="text-medium-emphasis mb-2">
            ナレーション本文内に以下の記法を入力すると、読み仮名や無音の長さ（間）を直接制御できます。
          </div>
          <div class="d-flex flex-column gap-1 font-mono">
            <div class="d-flex align-center gap-2">
              <code class="text-cyan px-1.5 py-0.5 rounded bg-black">｜漢字《よみ》</code>
              <span class="text-medium-emphasis">… ルビ（読み仮名）を直接指定（全角・半角どちらでも可）</span>
            </div>
            <div class="d-flex align-center gap-2">
              <code class="text-cyan px-1.5 py-0.5 rounded bg-black">［間］</code>
              <span class="text-medium-emphasis">… 0.5 秒のポーズを挿入</span>
            </div>
            <div class="d-flex align-center gap-2">
              <code class="text-cyan px-1.5 py-0.5 rounded bg-black">［間:1.5］</code>
              <span class="text-medium-emphasis">… 秒数を指定してポーズを挿入（最大 5.0 秒）</span>
            </div>
          </div>
        </v-card>
      </div>
    </v-expand-transition>

    <!-- ─── エラー表示 ─── -->
    <v-alert
      v-if="errorMessage"
      type="error"
      variant="tonal"
      density="compact"
      class="mb-3 text-caption"
      closable
      @click:close="errorMessage = ''"
    >
      {{ errorMessage }}
    </v-alert>

    <!-- ─── 読み上げテキストプレビュー領域 ─── -->
    <div v-if="readingData && readingData.text" class="reading-preview-card pa-3 rounded-lg mb-2">
      <div class="d-flex align-center justify-space-between mb-2">
        <span class="text-xxs text-medium-emphasis font-weight-bold text-uppercase">
          TTS 読み上げ用テキスト（単語をクリックして修正・登録）
        </span>

        <!-- 凡例 -->
        <div class="reading-legend d-flex align-center flex-wrap">
          <span class="legend-item legend-ruby">
            <span class="legend-dot">●</span>
            <span>ルビ指定</span>
          </span>
          <span class="legend-item legend-scene">
            <span class="legend-dot">●</span>
            <span>このシーンだけ</span>
          </span>
          <span class="legend-item legend-project">
            <span class="legend-dot">●</span>
            <span>プロジェクト辞書</span>
          </span>
          <span class="legend-item legend-global">
            <span class="legend-dot">●</span>
            <span>全体辞書</span>
          </span>
          <span class="legend-item legend-ai">
            <span class="legend-dot">●</span>
            <span>AI仮名化（要確認）</span>
          </span>
        </div>
      </div>

      <!-- ハイライト付きテキスト表示 -->
      <div class="reading-text-body font-mono text-body-2 leading-relaxed">
        <template v-for="(seg, idx) in segments" :key="idx">
          <!-- 通常のテキスト -->
          <span v-if="!seg.span">{{ seg.text }}</span>

          <!-- ハイライト対象の語（クリック可能） -->
          <v-tooltip
            v-else
            location="top"
            open-delay="200"
            max-width="320"
          >
            <template #activator="{ props: tooltipProps }">
              <span
                v-bind="tooltipProps"
                class="reading-span-badge cursor-pointer"
                :class="`span-${seg.span.source}`"
                @click="onSpanClick(seg.span)"
              >
                {{ seg.text }}
                <v-icon v-if="seg.span.source === 'ai'" size="12" class="ml-0.5">mdi-alert-circle-outline</v-icon>
              </span>
            </template>
            <div class="text-caption">
              <div class="font-weight-bold">{{ seg.span.surface }} → {{ seg.span.reading }}</div>
              <div class="text-medium-emphasis mt-0.5">種別: {{ sourceLabel(seg.span.source) }}</div>
              <div class="text-cyan mt-1">クリックしてルビ化または辞書登録</div>
            </div>
          </v-tooltip>
        </template>
      </div>
    </div>

    <!-- 未確認時のメッセージ表示 -->
    <div
      v-else-if="readingData && !readingData.ai_checked"
      class="text-caption text-medium-emphasis pa-3 rounded-lg bg-black-20 mb-2"
    >
      <v-icon size="14" class="mr-1">mdi-information-outline</v-icon>
      未確認（合成時に AI が自動で仮名化します）。「読みを確認」をクリックすると AI が判定した読み上げテキストをプレビューできます。
    </div>

    <!-- ─── 語をクリックしたときのアクションモーダル ─── -->
    <v-dialog v-model="actionModal" max-width="440">
      <v-card class="glass-card pa-2">
        <v-card-title class="d-flex align-center gap-2 text-subtitle-1 font-weight-bold">
          <v-icon color="#06b6d4" size="20">mdi-cog-outline</v-icon>
          <span>読みの修正・辞書登録</span>
        </v-card-title>

        <v-card-text class="pt-2">
          <div class="pa-3 rounded bg-black-20 mb-3">
            <div class="d-flex align-center justify-space-between mb-1">
              <span class="text-caption text-medium-emphasis">元の表記</span>
              <v-chip size="x-small" :color="sourceColor(selectedSpan?.source)" variant="tonal">
                {{ sourceLabel(selectedSpan?.source) }}
              </v-chip>
            </div>
            <div class="text-subtitle-1 font-weight-bold font-mono">{{ selectedSpan?.surface }}</div>

            <div class="text-caption text-medium-emphasis mt-2 mb-1">現在の読み上げ</div>
            <div class="text-subtitle-2 font-mono text-cyan font-weight-bold">{{ selectedSpan?.reading }}</div>
          </div>

          <div class="text-caption text-medium-emphasis mb-3">
            この単語の読みを変更したい場合は、以下のいずれかの操作を行ってください。
          </div>

          <div class="d-flex flex-column gap-2">
            <!-- 1. このシーンだけに登録 (#74) -->
            <v-btn
              variant="outlined"
              color="blue-lighten-1"
              class="justify-start py-2 h-auto text-left"
              prepend-icon="mdi-card-text-outline"
              :loading="savingDict === 'scene'"
              @click="openDictEditor('scene')"
            >
              <div>
                <div class="font-weight-bold text-caption">このシーンだけの読みに登録</div>
                <div class="text-xxs text-medium-emphasis">
                  このシーンのみに適用されます（本文に記号は入りません）
                </div>
              </div>
            </v-btn>

            <!-- 2. プロジェクト辞書に登録 -->
            <v-btn
              v-if="projectId"
              variant="outlined"
              color="success"
              class="justify-start py-2 h-auto text-left"
              prepend-icon="mdi-book-arrow-right-outline"
              :loading="savingDict === 'project'"
              @click="openDictEditor('project')"
            >
              <div>
                <div class="font-weight-bold text-caption">プロジェクト読み辞書に登録</div>
                <div class="text-xxs text-medium-emphasis">
                  このプロジェクト内の全動画で共通して適用されます
                </div>
              </div>
            </v-btn>

            <!-- 3. 全体辞書に登録 -->
            <v-btn
              variant="outlined"
              color="purple"
              class="justify-start py-2 h-auto text-left"
              prepend-icon="mdi-earth"
              :loading="savingDict === 'global'"
              @click="openDictEditor('global')"
            >
              <div>
                <div class="font-weight-bold text-caption">全体読み辞書に登録</div>
                <div class="text-xxs text-medium-emphasis">
                  システム全体のすべての動画で共通して適用されます
                </div>
              </div>
            </v-btn>

            <!-- 4. ルビに直す -->
            <v-btn
              variant="outlined"
              color="cyan"
              class="justify-start py-2 h-auto text-left"
              prepend-icon="mdi-format-letter-case"
              @click="openRubyEditor"
            >
              <div>
                <div class="font-weight-bold text-caption">本文をルビ表記にする（記号を挿入）</div>
                <div class="text-xxs text-medium-emphasis">
                  本文内の対象箇所を <code>｜{{ selectedSpan?.surface }}《読み》</code> に書き換えます
                </div>
              </div>
            </v-btn>
          </div>
        </v-card-text>

        <v-card-actions class="px-4 pb-3 justify-end">
          <v-btn variant="text" size="small" @click="actionModal = false">閉じる</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ─── ルビ指定エディタモーダル ─── -->
    <v-dialog v-model="rubyModal" max-width="420" persistent>
      <v-card class="glass-card pa-2">
        <v-card-title class="text-subtitle-1 font-weight-bold">
          ルビ（読み仮名）の指定
        </v-card-title>
        <v-card-text class="pt-2">
          <p class="text-caption text-medium-emphasis mb-3">
            本文の「<strong>{{ selectedSpan?.surface }}</strong>」をルビ記法に書き換えます。
          </p>

          <v-text-field
            v-model="rubyReadingInput"
            label="読み仮名"
            placeholder="例: けんじゃのいし"
            density="comfortable"
            hint="ひらがな、カタカナなど。記号 ｜《》［］ は使用できません"
            persistent-hint
            :rules="[v => !!v?.trim() || '読みを入力してください', v => !/[｜|《》［］[\]\n]/.test(v || '') || '記号は使えません']"
            autofocus
            class="mb-2"
          />

          <div class="pa-2 rounded bg-black-20 text-caption font-mono mt-3">
            変換結果: <span class="text-cyan font-weight-bold">｜{{ selectedSpan?.surface }}《{{ rubyReadingInput.trim() || 'よみ' }}》</span>
          </div>
        </v-card-text>
        <v-card-actions class="px-4 pb-3 justify-end gap-2">
          <v-btn variant="text" @click="rubyModal = false">キャンセル</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :disabled="!rubyReadingInput.trim() || /[｜|《》［］[\]\n]/.test(rubyReadingInput)"
            @click="applyRubyToNarration"
          >
            本文に反映する
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ─── 辞書登録エディタモーダル ─── -->
    <v-dialog v-model="dictModal" max-width="420" persistent>
      <v-card class="glass-card pa-2">
        <v-card-title class="text-subtitle-1 font-weight-bold">
          {{ dictModalTitle }}
        </v-card-title>
        <v-card-text class="pt-2">
          <v-alert
            v-if="dictError"
            type="error"
            variant="tonal"
            density="compact"
            class="mb-3 text-caption"
            closable
            @click:close="dictError = ''"
          >
            {{ dictError }}
          </v-alert>

          <!-- 409重複時の上書き確認アラート -->
          <v-alert
            v-if="existingEntryForOverwrite"
            type="warning"
            variant="tonal"
            density="compact"
            class="mb-3 text-caption"
          >
            「{{ dictForm.surface }}」は既に登録されています。読みを「{{ dictForm.reading }}」に上書きしますか？
          </v-alert>

          <v-text-field
            v-model="dictForm.surface"
            label="表記"
            density="comfortable"
            class="mb-3"
            :rules="[v => !!v?.trim() || '表記を入力してください', v => !/[｜|《》［］[\]\n]/.test(v || '') || '記号は使えません']"
          />

          <v-text-field
            v-model="dictForm.reading"
            label="読み"
            density="comfortable"
            class="mb-2"
            :rules="[v => !!v?.trim() || '読みを入力してください', v => !/[｜|《》［］[\]\n]/.test(v || '') || '記号は使えません']"
            autofocus
          />
        </v-card-text>
        <v-card-actions class="px-4 pb-3 justify-end gap-2">
          <v-btn variant="text" :disabled="savingDict !== null" @click="closeDictModal">キャンセル</v-btn>
          <v-btn
            v-if="existingEntryForOverwrite"
            color="warning"
            variant="flat"
            :loading="savingDict !== null"
            @click="submitOverwriteEntry"
          >
            上書きする
          </v-btn>
          <v-btn
            v-else
            color="primary"
            variant="flat"
            :loading="savingDict !== null"
            :disabled="!isDictFormValid"
            @click="submitDictRegistration"
          >
            登録する
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { readingApi } from '@/api/reading'
import { useUiStore } from '@/stores/ui'
import { useScenesStore } from '@/stores/scenes'

const props = defineProps({
  scene: {
    type: Object,
    required: true,
  },
  projectId: {
    type: String,
    default: null,
  },
  currentNarration: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['update:narration', 'applied'])

const ui = useUiStore()
const scenesStore = useScenesStore()

const loading = ref(false)
const errorMessage = ref('')
const showFormatHint = ref(false)
const readingData = ref(null)
const lastCheckedNarration = ref('')

// アクションモーダル・エディタモーダル
const actionModal = ref(false)
const selectedSpan = ref(null)

const rubyModal = ref(false)
const rubyReadingInput = ref('')

const dictModal = ref(false)
const targetDictType = ref('project')
const savingDict = ref(null)
const dictError = ref('')
const dictForm = ref({
  surface: '',
  reading: '',
})

const hasNarrationText = computed(() => {
  return Boolean(props.currentNarration && props.currentNarration.trim())
})

// ナレーションが変更されたかどうか
const isOutdated = computed(() => {
  if (!readingData.value) return false
  return (props.currentNarration || '') !== (lastCheckedNarration.value || '')
})

const isDictFormValid = computed(() => {
  const s = dictForm.value.surface?.trim()
  const r = dictForm.value.reading?.trim()
  if (!s || !r) return false
  if (/[｜|《》［］[\]\n]/.test(s) || /[｜|《》［］[\]\n]/.test(r)) return false
  return true
})

// text と spans を分割してセグメント化する
const segments = computed(() => {
  if (!readingData.value?.text) return []
  const text = readingData.value.text
  const spans = readingData.value.spans || []
  if (spans.length === 0) {
    return [{ text, span: null }]
  }

  const result = []
  let cursor = 0

  for (const span of spans) {
    if (span.start > cursor) {
      result.push({
        text: text.slice(cursor, span.start),
        span: null,
      })
    }
    result.push({
      text: text.slice(span.start, span.end),
      span,
    })
    cursor = span.end
  }

  if (cursor < text.length) {
    result.push({
      text: text.slice(cursor),
      span: null,
    })
  }

  return result
})

function sourceLabel(source) {
  switch (source) {
    case 'ruby':
      return 'ルビ指定'
    case 'scene':
      return 'このシーンだけ'
    case 'project':
      return 'プロジェクト辞書'
    case 'global':
      return '全体辞書'
    case 'ai':
      return 'AI仮名化'
    default:
      return source || '不明'
  }
}

function sourceColor(source) {
  switch (source) {
    case 'ruby':
      return 'cyan'
    case 'scene':
      return 'blue-lighten-1'
    case 'project':
      return 'success'
    case 'global':
      return 'purple'
    case 'ai':
      return 'warning'
    default:
      return 'grey'
  }
}

// 読み情報のフェッチ（AIは動かさない）
async function fetchReading() {
  if (!props.scene?.id) return
  try {
    const res = await readingApi.getSceneReading(props.scene.id)
    readingData.value = res.data
    lastCheckedNarration.value = props.scene.narration_text || ''
  } catch (e) {
    console.warn('Failed to fetch scene reading', e)
  }
}

// 「読みを確認」ボタン押下（AI仮名化を実行）
async function runReadingCheck() {
  if (!props.scene?.id) return
  loading.value = true
  errorMessage.value = ''

  try {
    // もし入力中のナレーションとDB保存値に差異があれば、先にDBを更新しておく
    if ((props.currentNarration || '') !== (props.scene.narration_text || '')) {
      await scenesStore.update(props.scene.id, { narration_text: props.currentNarration || '' })
      props.scene.narration_text = props.currentNarration || ''
    }

    const res = await readingApi.checkSceneReading(props.scene.id, true)
    readingData.value = res.data
    lastCheckedNarration.value = props.currentNarration || ''
    ui.notify('読みの確認が完了しました')
  } catch (e) {
    const msg = e.message || '読みの確認に失敗しました'
    errorMessage.value = msg
    ui.notifyError(msg)
  } finally {
    loading.value = false
  }
}

function onSpanClick(span) {
  selectedSpan.value = span
  actionModal.value = true
}

// 1. ルビに直す
function openRubyEditor() {
  actionModal.value = false
  rubyReadingInput.value = selectedSpan.value?.reading || ''
  rubyModal.value = true
}

function applyRubyToNarration() {
  if (!selectedSpan.value) return
  const span = selectedSpan.value
  const reading = rubyReadingInput.value.trim()
  if (!reading) return

  const curText = props.currentNarration || ''
  const start = span.src_start
  const end = span.src_end

  // ルビ記法: ｜表記《読み》
  const rubyMarkup = `｜${span.surface}《${reading}》`

  // 本文を置換
  const newText = curText.slice(0, start) + rubyMarkup + curText.slice(end)
  emit('update:narration', newText)
  emit('applied')

  rubyModal.value = false
  ui.notify(`「${span.surface}」をルビ記法に変換しました。保存または再確認を行ってください。`)
}

const dictModalTitle = computed(() => {
  if (targetDictType.value === 'scene') return 'このシーンだけの読みに登録'
  if (targetDictType.value === 'project') return 'プロジェクト読み辞書に登録'
  return '全体読み辞書に登録'
})

const existingEntryForOverwrite = ref(null)

function closeDictModal() {
  dictModal.value = false
  dictError.value = ''
  existingEntryForOverwrite.value = null
}

// 2, 3, & 4. 辞書登録
function openDictEditor(type) {
  actionModal.value = false
  targetDictType.value = type
  dictError.value = ''
  existingEntryForOverwrite.value = null
  dictForm.value = {
    surface: selectedSpan.value?.surface || '',
    reading: selectedSpan.value?.reading || '',
  }
  dictModal.value = true
}

async function findExistingEntry(type, surface) {
  try {
    let listRes
    if (type === 'scene') {
      listRes = await readingApi.listScene(props.scene.id)
    } else if (type === 'project') {
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

async function submitDictRegistration() {
  if (!isDictFormValid.value) return
  savingDict.value = targetDictType.value
  dictError.value = ''
  existingEntryForOverwrite.value = null

  const payload = {
    surface: dictForm.value.surface.trim(),
    reading: dictForm.value.reading.trim(),
  }

  try {
    if (targetDictType.value === 'scene') {
      await readingApi.createScene(props.scene.id, payload)
      ui.notify('このシーンの読みに登録しました')
    } else if (targetDictType.value === 'project') {
      if (!props.projectId) throw new Error('プロジェクトIDが指定されていません')
      await readingApi.createProject(props.projectId, payload)
      ui.notify('プロジェクト読み辞書に登録しました')
    } else {
      await readingApi.createGlobal(payload)
      ui.notify('全体読み辞書に登録しました')
    }
    closeDictModal()
    await fetchReading()
  } catch (e) {
    const msg = e.message || '辞書の登録に失敗しました'
    dictError.value = msg
    // 409（重複）の場合は上書き確認できるように既存エントリを探す
    if (msg.includes('すでにこの辞書にあります') || e.response?.status === 409) {
      const existing = await findExistingEntry(targetDictType.value, payload.surface)
      if (existing) {
        existingEntryForOverwrite.value = existing
      }
    }
    ui.notifyError(msg)
  } finally {
    savingDict.value = null
  }
}

async function submitOverwriteEntry() {
  if (!existingEntryForOverwrite.value) return
  savingDict.value = targetDictType.value
  dictError.value = ''

  const payload = {
    surface: dictForm.value.surface.trim(),
    reading: dictForm.value.reading.trim(),
  }

  try {
    await readingApi.updateEntry(existingEntryForOverwrite.value.id, payload)
    ui.notify('読み辞書を上書き更新しました')
    closeDictModal()
    await fetchReading()
  } catch (e) {
    const msg = e.message || '更新に失敗しました'
    dictError.value = msg
    ui.notifyError(msg)
  } finally {
    savingDict.value = null
  }
}

// シーン切り替え時・ナレーション更新時の監視
watch(() => [props.scene?.id, props.scene?.narration_text], ([newId, newText], [oldId, oldText]) => {
  if (newId) {
    if (newId !== oldId) errorMessage.value = ''
    fetchReading()
  } else {
    readingData.value = null
  }
}, { immediate: true })

defineExpose({
  fetchReading,
  runReadingCheck,
  readingData,
})
</script>

<style scoped>
.scene-reading-checker {
  transition: all 0.2s ease-in-out;
}

.reading-preview-card {
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.reading-text-body {
  word-break: break-all;
  line-height: 1.8;
}

/* 汎用 Gap ユーティリティ */
.gap-1 { gap: 4px !important; }
.gap-2 { gap: 8px !important; }
.gap-3 { gap: 12px !important; }

/* 凡例 */
.reading-legend {
  gap: 12px !important;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 0.72rem;
  background: rgba(255, 255, 255, 0.04);
  line-height: 1.4;
}
.legend-dot {
  font-size: 0.62rem;
  line-height: 1;
}
.legend-ruby {
  color: #22d3ee;
  border: 1px solid rgba(6, 182, 212, 0.3);
}
.legend-scene {
  color: #60a5fa;
  border: 1px solid rgba(59, 130, 246, 0.3);
}
.legend-project {
  color: #34d399;
  border: 1px solid rgba(16, 185, 129, 0.3);
}
.legend-global {
  color: #c084fc;
  border: 1px solid rgba(168, 85, 247, 0.3);
}
.legend-ai {
  color: #fbbf24;
  border: 1px solid rgba(245, 158, 11, 0.4);
  font-weight: 600;
}

/* Spans ハイライトスタイル */
.reading-span-badge {
  display: inline-block;
  padding: 1px 6px;
  margin: 1px 2px;
  border-radius: 4px;
  font-weight: 600;
  transition: all 0.15s ease;
  position: relative;
}

.reading-span-badge:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  filter: brightness(1.2);
}

/* ルビ指定 */
.span-ruby {
  background: rgba(6, 182, 212, 0.18);
  border: 1px solid rgba(6, 182, 212, 0.5);
  color: #22d3ee;
}

/* このシーンだけ (#74) */
.span-scene {
  background: rgba(59, 130, 246, 0.18);
  border: 1px solid rgba(59, 130, 246, 0.5);
  color: #93c5fd;
}

/* プロジェクト辞書 */
.span-project {
  background: rgba(16, 185, 129, 0.18);
  border: 1px solid rgba(16, 185, 129, 0.5);
  color: #34d399;
}

/* 全体辞書 */
.span-global {
  background: rgba(168, 85, 247, 0.18);
  border: 1px solid rgba(168, 85, 247, 0.5);
  color: #c084fc;
}

/* AI仮名化（要確認 - 特に目立たせる） */
.span-ai {
  background: rgba(245, 158, 11, 0.25);
  border: 1px dashed #f59e0b;
  color: #fbbf24;
  box-shadow: 0 0 8px rgba(245, 158, 11, 0.2);
}
.span-ai:hover {
  border-style: solid;
  box-shadow: 0 0 12px rgba(245, 158, 11, 0.4);
}

.bg-black-20 {
  background: rgba(0, 0, 0, 0.25);
}
</style>
