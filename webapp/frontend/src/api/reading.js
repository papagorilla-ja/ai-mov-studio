import { api, longApi } from './index'

export const readingApi = {
  // 全体辞書
  listGlobal: () => api.get('/reading-dictionary'),
  createGlobal: (payload) => api.post('/reading-dictionary', payload),

  // プロジェクト辞書
  listProject: (projectId) => api.get(`/projects/${projectId}/reading-dictionary`),
  createProject: (projectId, payload) => api.post(`/projects/${projectId}/reading-dictionary`, payload),

  // シーン辞書（#73, #74）
  listScene: (sceneId) => api.get(`/scenes/${sceneId}/reading-dictionary`),
  createScene: (sceneId, payload) => api.post(`/scenes/${sceneId}/reading-dictionary`, payload),

  // 項目更新・削除（全体・プロジェクト・シーン共通）
  updateEntry: (entryId, payload) => api.put(`/reading-dictionary/${entryId}`, payload),
  deleteEntry: (entryId) => api.delete(`/reading-dictionary/${entryId}`),

  // シーンの読み上げ用テキスト取得（AI は動かさない）
  getSceneReading: (sceneId) => api.get(`/scenes/${sceneId}/reading`),

  // シーンの読みを確認（AI による仮名化を実行）
  checkSceneReading: (sceneId, force = false) =>
    longApi.post(`/scenes/${sceneId}/reading-check`, null, { params: { force } }),

  // 読みの推定（#73, #74）
  guessSceneReading: (sceneId, surface) =>
    api.post(`/scenes/${sceneId}/reading-guess`, { surface }),

  // 書式の点検（#73, #74）
  inspectMarkup: (text) =>
    api.post('/reading/inspect', { text }),
}
