<template>
  <v-card class="mb-4 glass-card">
    <v-card-title class="d-flex align-center justify-space-between flex-wrap text-body-1 font-weight-medium pa-4 gap-2">
      <div class="d-flex align-center gap-2">
        <v-icon color="#06b6d4" size="20">mdi-book-alphabet</v-icon>
        <span>{{ displayTitle }}</span>
        <v-chip size="x-small" variant="tonal" color="cyan" class="font-weight-bold ml-1">
          {{ filteredEntries.length }} 件
        </v-chip>
      </div>

      <div class="d-flex align-center gap-2">
        <v-btn
          size="small"
          color="primary"
          prepend-icon="mdi-plus"
          @click="openAddDialog"
        >
          単語を追加
        </v-btn>
      </div>
    </v-card-title>

    <v-card-text>
      <p v-if="displayDescription" class="text-caption text-medium-emphasis mb-3">
        {{ displayDescription }}
      </p>

      <!-- 検索フィルター -->
      <div v-if="entries.length > 5" class="mb-3">
        <v-text-field
          v-model="searchQuery"
          placeholder="表記または読みで検索..."
          density="compact"
          variant="outlined"
          prepend-inner-icon="mdi-magnify"
          clearable
          hide-details
        />
      </div>

      <!-- ローディング -->
      <div v-if="loading" class="d-flex justify-center py-6">
        <v-progress-circular indeterminate color="primary" />
      </div>

      <!-- 空状態 -->
      <div v-else-if="entries.length === 0" class="text-center py-6 text-medium-emphasis">
        <v-icon size="36" class="mb-2 opacity-50">mdi-book-open-outline</v-icon>
        <div class="text-body-2">登録されている単語はありません</div>
        <div class="text-caption mt-1">
          よく読み間違えられる固有名詞や専門用語の表記と読みを登録できます。
        </div>
      </div>

      <!-- 一覧テーブル -->
      <v-table v-else density="compact" class="bg-transparent reading-table">
        <thead>
          <tr>
            <th class="text-left font-weight-bold">表記</th>
            <th class="text-left font-weight-bold">読み（ひらがな・カタカナ等）</th>
            <th class="text-left font-weight-bold" style="width: 140px;">更新日時</th>
            <th class="text-right font-weight-bold" style="width: 100px;">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in filteredEntries" :key="entry.id" class="reading-row">
            <td class="font-weight-bold font-mono">{{ entry.surface }}</td>
            <td class="text-cyan font-mono">{{ entry.reading }}</td>
            <td class="text-caption text-medium-emphasis">{{ formatDate(entry.updated_at) }}</td>
            <td class="text-right">
              <div class="d-flex align-center justify-end gap-1">
                <v-btn
                  icon="mdi-pencil-outline"
                  size="x-small"
                  variant="text"
                  color="primary"
                  title="編集"
                  @click="openEditDialog(entry)"
                />
                <v-btn
                  icon="mdi-delete-outline"
                  size="x-small"
                  variant="text"
                  color="error"
                  title="削除"
                  @click="confirmDelete(entry)"
                />
              </div>
            </td>
          </tr>
          <tr v-if="filteredEntries.length === 0 && searchQuery">
            <td colspan="4" class="text-center py-4 text-medium-emphasis text-caption">
              検索条件に一致する単語は見つかりませんでした
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card-text>

    <!-- ─── 追加・編集ダイアログ ─── -->
    <v-dialog v-model="dialog" max-width="480" persistent>
      <v-card class="glass-card pa-2">
        <v-card-title class="d-flex align-center gap-2 text-subtitle-1 font-weight-bold">
          <v-icon color="#06b6d4" size="20">
            {{ isEditing ? 'mdi-pencil' : 'mdi-plus-circle' }}
          </v-icon>
          <span>{{ isEditing ? '単語の読みを編集' : '新しい単語を辞書に登録' }}</span>
        </v-card-title>

        <v-card-text class="pt-2">
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

          <v-text-field
            v-model="form.surface"
            label="表記（例: 賢者の石）"
            hint="50文字以内。記号 ｜《》［］ や改行は使用できません。"
            persistent-hint
            :rules="[rules.required, rules.maxLength(50), rules.noMarkup]"
            density="comfortable"
            class="mb-3"
            autofocus
          />

          <v-text-field
            v-model="form.reading"
            label="読み（例: けんじゃのいし）"
            hint="100文字以内。記号 ｜《》［］ や改行は使用できません。"
            persistent-hint
            :rules="[rules.required, rules.maxLength(100), rules.noMarkup]"
            density="comfortable"
            class="mb-2"
          />
        </v-card-text>

        <v-card-actions class="px-4 pb-3 justify-end gap-2">
          <v-btn variant="text" :disabled="saving" @click="closeDialog">
            キャンセル
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="saving"
            :disabled="!isFormValid"
            @click="saveEntry"
          >
            {{ isEditing ? '更新' : '登録' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ─── 削除確認ダイアログ ─── -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card class="glass-card pa-2">
        <v-card-title class="text-subtitle-1 font-weight-bold">
          単語の削除
        </v-card-title>
        <v-card-text class="text-body-2">
          「<strong>{{ targetEntry?.surface }}</strong>」を辞書から削除してもよろしいですか？
        </v-card-text>
        <v-card-actions class="px-4 pb-3 justify-end gap-2">
          <v-btn variant="text" :disabled="deleting" @click="deleteDialog = false">
            キャンセル
          </v-btn>
          <v-btn color="error" variant="flat" :loading="deleting" @click="deleteEntry">
            削除
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { readingApi } from '../api/reading'
import { useUiStore } from '../stores/ui'

const props = defineProps({
  projectId: {
    type: String,
    default: null,
  },
  title: {
    type: String,
    default: '',
  },
  description: {
    type: String,
    default: '',
  },
})

const ui = useUiStore()

const entries = ref([])
const loading = ref(false)
const searchQuery = ref('')

const dialog = ref(false)
const isEditing = ref(false)
const saving = ref(false)
const errorMessage = ref('')
const form = ref({
  id: null,
  surface: '',
  reading: '',
})

const deleteDialog = ref(false)
const deleting = ref(false)
const targetEntry = ref(null)

const displayTitle = computed(() => {
  if (props.title) return props.title
  return props.projectId ? 'プロジェクト読み辞書' : '全体読み辞書'
})

const displayDescription = computed(() => {
  if (props.description) return props.description
  return props.projectId
    ? 'このプロジェクト内の全動画で共通して適用される読みの辞書です。全体辞書より優先されます。'
    : 'システム全体の全動画で共通して適用される読みの辞書です。'
})

const MARKUP_CHARS = /[｜|《》［］[\]\n]/

const rules = {
  required: v => Boolean(v && v.trim()) || '入力してください',
  maxLength: max => v => (!v || v.length <= max) || `${max}文字以内で入力してください`,
  noMarkup: v => !MARKUP_CHARS.test(v || '') || '記号 ｜《》［］ や改行は使えません',
}

const isFormValid = computed(() => {
  const s = form.value.surface?.trim()
  const r = form.value.reading?.trim()
  if (!s || !r) return false
  if (s.length > 50 || r.length > 100) return false
  if (MARKUP_CHARS.test(s) || MARKUP_CHARS.test(r)) return false
  return true
})

const filteredEntries = computed(() => {
  if (!searchQuery.value?.trim()) return entries.value
  const q = searchQuery.value.trim().toLowerCase()
  return entries.value.filter(e =>
    e.surface.toLowerCase().includes(q) || e.reading.toLowerCase().includes(q)
  )
})

function formatDate(isoStr) {
  if (!isoStr) return '-'
  try {
    const d = new Date(isoStr)
    return d.toLocaleDateString('ja-JP', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return isoStr
  }
}

async function fetchEntries() {
  loading.value = true
  try {
    const res = props.projectId
      ? await readingApi.listProject(props.projectId)
      : await readingApi.listGlobal()
    entries.value = res.data || []
  } catch (e) {
    ui.notifyError('読み辞書の取得に失敗しました: ' + (e.message || ''))
  } finally {
    loading.value = false
  }
}

function openAddDialog() {
  isEditing.value = false
  errorMessage.value = ''
  form.value = {
    id: null,
    surface: '',
    reading: '',
  }
  dialog.value = true
}

function openEditDialog(entry) {
  isEditing.value = true
  errorMessage.value = ''
  form.value = {
    id: entry.id,
    surface: entry.surface,
    reading: entry.reading,
  }
  dialog.value = true
}

function closeDialog() {
  dialog.value = false
  errorMessage.value = ''
}

async function saveEntry() {
  if (!isFormValid.value) return
  saving.value = true
  errorMessage.value = ''

  const payload = {
    surface: form.value.surface.trim(),
    reading: form.value.reading.trim(),
  }

  try {
    if (isEditing.value) {
      await readingApi.updateEntry(form.value.id, payload)
      ui.notify('辞書の項目を更新しました')
    } else {
      if (props.projectId) {
        await readingApi.createProject(props.projectId, payload)
      } else {
        await readingApi.createGlobal(payload)
      }
      ui.notify('辞書に登録しました')
    }
    dialog.value = false
    await fetchEntries()
  } catch (e) {
    const msg = e.message || '保存に失敗しました'
    errorMessage.value = msg
    ui.notifyError(msg)
  } finally {
    saving.value = false
  }
}

function confirmDelete(entry) {
  targetEntry.value = entry
  deleteDialog.value = true
}

async function deleteEntry() {
  if (!targetEntry.value) return
  deleting.value = true
  try {
    await readingApi.deleteEntry(targetEntry.value.id)
    ui.notify('辞書から削除しました')
    deleteDialog.value = false
    await fetchEntries()
  } catch (e) {
    ui.notifyError('削除に失敗しました: ' + (e.message || ''))
  } finally {
    deleting.value = false
  }
}

watch(() => props.projectId, () => {
  fetchEntries()
})

onMounted(() => {
  fetchEntries()
})

defineExpose({
  fetchEntries,
  openAddDialogWith: (surface, reading) => {
    isEditing.value = false
    errorMessage.value = ''
    form.value = {
      id: null,
      surface: surface || '',
      reading: reading || '',
    }
    dialog.value = true
  }
})
</script>

<style scoped>
.reading-table {
  border-radius: 8px;
  overflow: hidden;
}
.reading-row:hover {
  background: rgba(255, 255, 255, 0.03);
}
</style>
