/**
 * 1 テイクの録音を扱う composable（#11）
 *
 * 設定画面の「音声収集セッション」と、ローカル録音ツール（#12）が共通で使う。
 * 録音の状態は次のように進む。
 *
 *   idle ─録音ボタン→ countdown（3 秒・ノイズ学習）→ recording ─停止→ processing → done
 *                      └ カウントダウン中に停止したら取り消して idle に戻る
 *
 * done になると、ノイズ除去後の音と元の音を聴き比べたり、強さを変えて処理し直したりできる。
 */
import { computed, getCurrentInstance, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { COUNTDOWN_SEC, DEFAULT_NOISE_REDUCTION, MAX_RECORDING_SEC, TARGET_SAMPLE_RATE } from '@/audio/config.js'
import { describeMicrophoneError, isMicrophoneSupported, listMicrophones, startCapture } from '@/audio/capture.js'
import { applyNoiseReduction, buildTake } from '@/audio/takeProcessing.js'
import { drawIdleWaveform, startLiveWaveform } from '@/audio/waveform.js'
import { encodeWav, encodeWavBlob } from '@/audio/wav.js'

// カウントダウン・経過秒数の表示を更新する間隔（ミリ秒）
const TICK_MS = 100

/**
 * @param {object} [options]
 * @param {import('vue').Ref<HTMLCanvasElement|null>} [options.canvasRef] 波形を描く canvas
 */
export function useVoiceTakeRecorder({ canvasRef } = {}) {
  /** @type {import('vue').Ref<'idle'|'countdown'|'recording'|'processing'|'done'>} */
  const phase = ref('idle')
  const countdownLeft = ref(0)           // カウントダウンの残り秒（3, 2, 1）
  const elapsedSec = ref(0)              // 発話を受け付けてからの経過秒
  const microphones = ref([])            // [{ deviceId, label }]
  const microphoneId = ref('')           // '' は既定のマイク
  const noiseReduction = ref(DEFAULT_NOISE_REDUCTION)
  const take = shallowRef(null)          // takeProcessing.buildTake() の結果
  const processed = shallowRef(null)     // ノイズ除去後の音声（Float32Array）
  const playing = ref(null)              // 再生中の音: 'processed' / 'original' / null

  const isCapturing = computed(() => phase.value === 'countdown' || phase.value === 'recording')
  const isBusy = computed(() => isCapturing.value || phase.value === 'processing')
  const hasTake = computed(() => phase.value === 'done' && take.value !== null)
  const warnings = computed(() => take.value?.analysis.warnings ?? [])
  const durationSec = computed(() => (take.value ? Math.round(take.value.durationSec * 10) / 10 : 0))

  let capture = null          // capture.startCapture() の戻り値
  let starting = false        // マイクの準備中（許可ダイアログの表示中など）。二重に始めないための印
  // reset() のたびに増やす番号。マイクの準備中や処理中に reset() されたとき、
  // 後から終わった古い処理の結果を捨てるために使う
  let generation = 0
  let startedAt = 0           // 録音を始めた時刻（performance.now()）
  let tickTimer = null
  let stopWaveform = null
  let audio = null            // 再生用の Audio 要素（多重再生を避けるため 1 つだけ）
  const objectUrls = { original: null, processed: null }

  // ─── 波形 ───────────────────────────────────────────
  function drawIdle() {
    if (canvasRef?.value) drawIdleWaveform(canvasRef.value)
  }
  // canvas が表示されたら（ダイアログを開いた・手順を進めたなど）、待機中の表示を描く
  if (canvasRef) watch(canvasRef, drawIdle, { flush: 'post' })

  // ─── 再生 ───────────────────────────────────────────
  function revokeUrl(kind) {
    if (objectUrls[kind]) URL.revokeObjectURL(objectUrls[kind])
    objectUrls[kind] = null
  }

  function stopPlayback() {
    if (audio) {
      audio.pause()
      audio = null
    }
    playing.value = null
  }

  /**
   * 録音した音を再生する。
   * @param {'processed'|'original'} kind
   * @returns {Promise<void>} 再生を始められなければ reject する
   */
  function play(kind) {
    stopPlayback()
    const samples = kind === 'original' ? take.value?.original : processed.value
    if (!samples) return Promise.resolve()
    if (!objectUrls[kind]) objectUrls[kind] = URL.createObjectURL(encodeWavBlob(samples, TARGET_SAMPLE_RATE))

    const current = new Audio(objectUrls[kind])
    audio = current
    playing.value = kind
    current.onended = () => {
      if (audio === current) stopPlayback()
    }
    return current.play().catch((e) => {
      if (audio === current) stopPlayback()
      throw e
    })
  }

  // ─── ノイズ除去 ─────────────────────────────────────
  function reprocess() {
    if (!take.value) return
    stopPlayback()
    revokeUrl('processed')
    processed.value = applyNoiseReduction(take.value, noiseReduction.value)
  }
  // 録音後に強さを変えたら、元の音から処理し直す
  watch(noiseReduction, reprocess)

  // ─── 録音 ───────────────────────────────────────────
  async function refreshMicrophones() {
    try {
      microphones.value = await listMicrophones()
    } catch {
      microphones.value = []
    }
  }

  function clearTimers() {
    if (tickTimer) {
      clearInterval(tickTimer)
      tickTimer = null
    }
    if (stopWaveform) {
      stopWaveform()
      stopWaveform = null
    }
  }

  function tick() {
    const sec = (performance.now() - startedAt) / 1000
    if (sec < COUNTDOWN_SEC) {
      countdownLeft.value = Math.ceil(COUNTDOWN_SEC - sec)
      return
    }
    phase.value = 'recording'
    countdownLeft.value = 0
    elapsedSec.value = Math.floor(sec - COUNTDOWN_SEC)
    // 止め忘れ対策。上限に達したら自動で止める（結果は phase の変化で画面に出る）
    if (sec - COUNTDOWN_SEC >= MAX_RECORDING_SEC) {
      stop().catch(e => console.error('録音の自動停止後の処理に失敗しました:', e))
    }
  }

  /** 録音済みのテイクを捨てて待機状態に戻す（録音中は何もしない）。 */
  function discard() {
    if (isBusy.value) return
    stopPlayback()
    revokeUrl('original')
    revokeUrl('processed')
    take.value = null
    processed.value = null
    countdownLeft.value = 0
    elapsedSec.value = 0
    phase.value = 'idle'
    drawIdle()
  }

  /**
   * 録音を始める（カウントダウンから）。マイクを使えないときは、利用者向けの文言で reject する。
   */
  async function start() {
    if (isBusy.value || starting) return
    discard()
    if (!isMicrophoneSupported()) {
      throw new Error('このブラウザ・この URL ではマイクを使用できません。')
    }

    const myGeneration = generation
    let started
    starting = true
    try {
      started = await startCapture(microphoneId.value)
    } catch (e) {
      throw new Error(describeMicrophoneError(e))
    } finally {
      starting = false
    }
    // 許可を待っている間にダイアログが閉じられた（reset された）ら、すぐにマイクを解放する
    if (myGeneration !== generation) {
      started.stop()
      return
    }

    capture = started
    phase.value = 'countdown'
    countdownLeft.value = COUNTDOWN_SEC
    elapsedSec.value = 0
    startedAt = performance.now()
    tickTimer = setInterval(tick, TICK_MS)
    if (canvasRef?.value) stopWaveform = startLiveWaveform(canvasRef.value, capture.analyser)
    // マイクを許可した後でないとデバイス名が取れないため、ここで一覧を取り直す
    refreshMicrophones()
  }

  /**
   * 録音を止めて処理する。
   * @returns {Promise<'done'|'cancelled'|'empty'|undefined>}
   *   done … テイクができた /
   *   cancelled … カウントダウン中に止めた、または処理中に reset されたので取り消した /
   *   empty … 発話の区間が無かった / undefined … 録音していなかった
   */
  async function stop() {
    if (!isCapturing.value || !capture) return undefined
    const wasCountdown = phase.value === 'countdown'
    clearTimers()
    const recorded = capture.stop()
    capture = null
    drawIdle()

    if (wasCountdown) {
      phase.value = 'idle'
      return 'cancelled'
    }

    phase.value = 'processing'
    const myGeneration = generation
    try {
      const built = await buildTake(recorded)
      // 処理中に reset された場合は、結果を捨てる（閉じたダイアログにテイクを復活させない）
      if (myGeneration !== generation) return 'cancelled'
      if (!built) {
        phase.value = 'idle'
        return 'empty'
      }
      take.value = built
      phase.value = 'done'
      reprocess()
      return 'done'
    } catch (e) {
      if (myGeneration !== generation) return 'cancelled'
      phase.value = 'idle'
      throw e
    }
  }

  /** 録音中なら破棄してマイクを解放し、テイクも捨てる（ダイアログを閉じるとき・画面を離れるとき）。 */
  function reset() {
    generation++
    clearTimers()
    if (capture) {
      capture.stop()
      capture = null
    }
    phase.value = 'idle'
    discard()
  }
  if (getCurrentInstance()) onBeforeUnmount(reset)

  // 以前にマイクを許可済みなら、最初の録音の前からマイクを選べるよう一覧を取っておく
  refreshMicrophones()

  // ─── 書き出し ───────────────────────────────────────
  /** ノイズ除去後の音を WAV の Blob で返す（サーバーへのアップロード用）。 */
  function processedWavBlob() {
    return processed.value ? encodeWavBlob(processed.value, TARGET_SAMPLE_RATE) : null
  }

  /** ノイズ除去後の音を WAV のバイト列で返す（録音ツールの zip 用）。 */
  function processedWavBytes() {
    return processed.value ? encodeWav(processed.value, TARGET_SAMPLE_RATE) : null
  }

  return {
    // 状態
    phase,
    countdownLeft,
    elapsedSec,
    microphones,
    microphoneId,
    noiseReduction,
    playing,
    isCapturing,
    isBusy,
    hasTake,
    warnings,
    durationSec,
    // 操作
    refreshMicrophones,
    start,
    stop,
    discard,
    reset,
    play,
    stopPlayback,
    processedWavBlob,
    processedWavBytes,
  }
}
