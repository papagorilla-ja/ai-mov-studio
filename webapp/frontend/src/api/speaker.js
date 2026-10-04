import { api, longApi } from './index'

export const speakerApi = {
  list: () => api.get('/speakers'),

  get: (id) => api.get(`/speakers/${id}`),

  create: (payload) => api.post('/speakers', payload),

  update: (id, payload) => api.patch(`/speakers/${id}`, payload),

  delete: (id) => api.delete(`/speakers/${id}`),

  // clean: 雑音を除去して整えるか（#10）。false なら 16kHz モノラルへの変換だけを行う
  uploadReference: (speakerId, file, clean = true) => {
    const form = new FormData()
    form.append('speaker_id', speakerId)
    form.append('file', file)
    form.append('clean', clean ? 'true' : 'false')
    // multipart を明示しないと、axios の既定 Content-Type(application/json) により
    // FormData が JSON へ変換されてしまい、サーバ側で 422 になる
    return api.post('/speakers/upload-reference', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  // ─── 音声収集セッション ───
  // 固定コーパスから出題するため待ち時間は発生しない（通常の api で十分）
  sessionModes: () => api.get('/speakers/collection-session/modes'),

  // 録音ツール（#12）に埋め込む提示項目（全モード・最大本数ぶん）
  sessionCorpus: () => api.get('/speakers/collection-session/corpus'),

  sessionStart: (mode = 'script', itemCount = 5) =>
    api.post('/speakers/collection-session/start', { mode, item_count: itemCount }),

  sessionRecord: (sessionId, sentenceIndex, audioBlob, fileName = 'take') => {
    const form = new FormData()
    form.append('sentence_index', sentenceIndex)
    // 実際の形式はブラウザ依存（Chrome:webm / Safari:mp4）。拡張子は使わずサーバ側で判定させる
    form.append('file', audioBlob, fileName)
    // multipart を明示（既定の application/json のままだと FormData が JSON 化され 422 になる）
    return longApi.post(`/speakers/collection-session/${sessionId}/record`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  // 収録完了 → 収録音声ライブラリへ名前付きで保存（話者はここでは作らない）
  sessionFinalize: (sessionId, payload) =>
    longApi.post(`/speakers/collection-session/${sessionId}/finalize`, payload),

  // ─── 収録音声ライブラリ ───
  listRecordings: () => api.get('/speakers/recordings'),

  // 録音ツールで保存した収録データ（.zip）を取り込む（#12）。name が空ならツールで付けた名前を使う
  importRecording: (file, name = '') => {
    const form = new FormData()
    form.append('file', file)
    form.append('name', name)
    // multipart を明示（既定の application/json のままだと FormData が JSON 化され 422 になる）。
    // 全テイクの変換と連結を行うため、時間のかかる処理用のクライアントを使う
    return longApi.post('/speakers/recordings/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  renameRecording: (recordingId, name) =>
    api.patch(`/speakers/recordings/${recordingId}`, { name }),

  deleteRecording: (recordingId) =>
    api.delete(`/speakers/recordings/${recordingId}`),

  // 収録音声を話者の参照音声として採用する
  useRecording: (speakerId, recordingId) =>
    api.post('/speakers/use-recording', { speaker_id: speakerId, recording_id: recordingId }),
}
