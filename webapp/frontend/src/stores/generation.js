import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, withBase, getBasePrefix } from '@/api/index.js'
import { useUiStore } from './ui'
import { useScenesStore } from './scenes'
import { useVideosStore } from './videos'

export const useGenerationStore = defineStore('generation', () => {
  const histories = ref([])
  const currentProgress = ref(null)
  const currentGenerationId = ref(null)
  // レンダリング待ちの間に流す「音声なしの下見」の URL。
  // まだ用意できていない間は null で、画面側は何も出さない。
  const previewUrl = ref(null)
  const loading = ref(false)
  const ui = useUiStore()
  let ws = null
  let pollTimer = null

  function clearTimers() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function fetchHistories(videoId) {
    loading.value = true
    try {
      const { data } = await api.get(`/videos/${videoId}/generations`)
      histories.value = data
    } catch (e) {
      ui.notifyError(e.message)
    } finally {
      loading.value = false
    }
  }

  // 下見の URL を取りに行く。レンダリング開始の直前に用意されるため、
  // それより前に呼ぶと available=false が返る。
  // 下見は演出なので、取れなくてもエラーは出さずに黙って出さないだけにする。
  async function fetchPreview(videoId) {
    try {
      const { data } = await api.get(`/videos/${videoId}/preview`)
      // サブパス運用時でも iframe が読み込めるよう withBase で解決する
      previewUrl.value = data.available ? withBase(data.url) : null
    } catch (e) {
      previewUrl.value = null
    }
  }

  // 生成終了時（完了・失敗・中止）の共通後処理
  async function onGenerationFinished(videoId, status, details = {}) {
    clearTimers()
    if (ws) {
      ws.close()
      ws = null
    }
    previewUrl.value = null

    // 履歴と動画情報の取り直し
    await fetchHistories(videoId)
    const videosStore = useVideosStore()
    await videosStore.fetchOne(videoId)

    if (status === 'completed') {
      ui.notify('動画生成が完了しました！')
      try {
        const scenesStore = useScenesStore()
        await scenesStore.fetchAll(videoId)
      } catch (e) {
        console.warn('Failed to refresh scenes after generation', e)
      }
      const latest = histories.value[0]
      if (latest?.audio_warnings && latest.audio_warnings.length > 0) {
        const scenesList = latest.audio_warnings.map(w => `シーン ${w.scene_index}`).join('、')
        ui.notify(`${scenesList} の音声が崩れている可能性があります。シーン編集で音声を作り直してください`, 'warning', 8000)
      }
    } else if (status === 'cancelled') {
      ui.notify('動画生成を中止しました', 'info')
    } else if (status === 'failed') {
      const errMsg = details.error || details.message || '生成に失敗しました'
      ui.notifyError('動画生成エラー: ' + errMsg)
    }
  }

  // 生成中に WebSocket が切れた場合のポーリング＆再接続
  function startPollingAndReconnect(videoId) {
    clearTimers()
    pollTimer = setInterval(async () => {
      try {
        const { data } = await api.get(`/videos/${videoId}/generation-status`)
        if (data) {
          if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
            currentProgress.value = {
              generation_id: data.id,
              status: data.status,
              step: data.status === 'completed' ? 'completed' : (data.status === 'cancelled' ? 'cancelled' : 'failed'),
              progress: 1.0,
              message: data.status === 'completed' ? '生成完了' : (data.status === 'cancelled' ? '生成中止' : (data.error_message || '生成失敗')),
              error: data.status === 'failed' ? data.error_message : null
            }
            await onGenerationFinished(videoId, data.status, {
              error: data.status === 'failed' ? data.error_message : null
            })
            return
          }
        }
      } catch (e) {
        console.warn('Polling generation-status failed', e)
      }

      // まだ実行中なら再接続を試行
      if (!ws || ws.readyState === WebSocket.CLOSED) {
        connectWebSocket(videoId)
      }
    }, 3000)
  }

  // regenerateAudio=true で既存のナレーション音声を削除してから合成し直す
  async function generate(videoId, regenerateAudio = false) {
    loading.value = true
    previewUrl.value = null
    clearTimers()
    try {
      const { data } = await api.post(
        `/videos/${videoId}/generate?regenerate_audio=${regenerateAudio}`
      )
      currentGenerationId.value = data.generation_id
      currentProgress.value = {
        generation_id: data.generation_id,
        status: 'running',
        step: 'queued',
        progress: 0.0,
        message: '生成の準備をしています...',
        elapsed_sec: 0,
        stage_eta_sec: null
      }

      ui.notify(
        regenerateAudio
          ? '音声を再作成して動画生成を開始しました'
          : '動画生成プロセスを開始しました'
      )

      // 生成開始時に videosStore.fetchOne と fetchHistories を取り直す
      const videosStore = useVideosStore()
      await Promise.all([
        fetchHistories(videoId),
        videosStore.fetchOne(videoId)
      ])

      connectWebSocket(videoId)
      return data
    } catch (e) {
      ui.notifyError(e.message)
      throw e
    } finally {
      loading.value = false
    }
  }

  // 実行中の生成を中止する
  async function cancel(videoId) {
    loading.value = true
    try {
      await api.post(`/videos/${videoId}/generation/cancel`)
      ui.notify('動画生成を中止しています...')
    } catch (e) {
      ui.notifyError('動画生成の中止に失敗しました: ' + (e.response?.data?.detail || e.message))
    } finally {
      loading.value = false
    }
  }

  function connectWebSocket(videoId) {
    if (ws) {
      ws.close()
    }
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    // サブパス運用時（例: /ai-mov-studio）でも届くようベースプレフィックスを反映
    const prefix = getBasePrefix()
    const wsUrl = `${protocol}//${window.location.host}${prefix}/ws/videos/${videoId}/generation-progress`
    
    ws = new WebSocket(wsUrl)
    ws.onmessage = async (event) => {
      try {
        const data = JSON.parse(event.data)
        // generation_id が今の生成と違う進捗は無視する
        if (currentGenerationId.value && data.generation_id && data.generation_id !== currentGenerationId.value) {
          return
        }
        if (!currentGenerationId.value && data.generation_id) {
          currentGenerationId.value = data.generation_id
        }

        currentProgress.value = data

        if (data.status === 'cancelled') {
          await onGenerationFinished(videoId, 'cancelled')
        } else if (data.status === 'failed') {
          await onGenerationFinished(videoId, 'failed', {
            error: data.error || data.message
          })
        } else if (data.status === 'completed') {
          await onGenerationFinished(videoId, 'completed')
        } else if (data.status === 'running') {
          if (data.step === 'rendering' && !previewUrl.value) {
            // レンダリングに入った時点で下見が揃っている。1 度だけ取る
            fetchPreview(videoId)
          }
        }
      } catch (e) {
        console.error('WS Parse Error', e)
      }
    }
    ws.onclose = () => {
      console.log('WS Connection Closed')
      // 生成中のまま切断された場合はポーリング＆再接続を開始
      if (currentProgress.value?.status === 'running') {
        startPollingAndReconnect(videoId)
      }
    }
    ws.onerror = (err) => {
      console.warn('WS Error', err)
    }
  }

  function disconnectWebSocket() {
    clearTimers()
    if (ws) {
      ws.close()
      ws = null
    }
  }

  async function fetchGenerationStatus(videoId) {
    try {
      const { data } = await api.get(`/videos/${videoId}/generation-status`)
      if (data) {
        currentGenerationId.value = data.id
        if (data.status === 'running') {
          currentProgress.value = {
            generation_id: data.id,
            status: 'running',
            step: 'queued',
            progress: 0.05,
            message: '動画を生成中...',
            elapsed_sec: 0,
            stage_eta_sec: null
          }
          connectWebSocket(videoId)
          // すでにレンダリング段階なら下見がある
          fetchPreview(videoId)
        } else if (data.status === 'completed') {
          currentProgress.value = {
            generation_id: data.id,
            status: 'completed',
            step: 'completed',
            progress: 1.0,
            message: '生成完了'
          }
        } else if (data.status === 'failed') {
          currentProgress.value = {
            generation_id: data.id,
            status: 'failed',
            step: 'failed',
            progress: 1.0,
            message: '生成失敗',
            error: data.error_message
          }
        } else if (data.status === 'cancelled') {
          currentProgress.value = {
            generation_id: data.id,
            status: 'cancelled',
            step: 'cancelled',
            progress: 1.0,
            message: '生成中止'
          }
        }
      }
    } catch (e) {
      console.warn('fetchGenerationStatus error', e)
    }
  }

  async function remove(generationId) {
    loading.value = true
    try {
      await api.delete(`/generations/${generationId}`)
      histories.value = histories.value.filter(h => h.id !== generationId)
      ui.notify('生成履歴を削除しました')
    } catch (e) {
      ui.notifyError(e.message)
    } finally {
      loading.value = false
    }
  }

  function downloadUrl(generationId) {
    return `${api.defaults.baseURL}/generations/${generationId}/download`
  }

  function playUrl(generationId) {
    return `${api.defaults.baseURL}/generations/${generationId}/play`
  }

  return {
    histories,
    currentProgress,
    currentGenerationId,
    previewUrl,
    loading,
    fetchHistories,
    fetchGenerationStatus,
    fetchPreview,
    generate,
    cancel,
    remove,
    connectWebSocket,
    disconnectWebSocket,
    downloadUrl,
    playUrl
  }
})

