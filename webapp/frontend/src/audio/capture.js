/**
 * マイクからの録音エンジン（#11）
 *
 * MediaRecorder（圧縮形式）ではなく、非圧縮の PCM でそのまま受け取る。
 *   - 端のカットやノイズの学習を、サンプル単位の正確な位置で行える
 *   - 圧縮による音質の劣化が、声質クローンの参照音声に入らない
 *
 * 受け取りには AudioWorklet を使い、使えない環境（file:// で開いたツールで
 * Blob の読み込みが拒否された場合など）では ScriptProcessorNode に切り替える。
 */

// AudioWorklet の処理本体。ツールを単一 HTML に保つため、別ファイルにせず文字列で持つ
const WORKLET_NAME = 'voice-capture'
const WORKLET_SOURCE = `
class VoiceCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    // 128 サンプルごとに送ると通信が多すぎるので、ある程度ためてから送る
    this.buffer = new Float32Array(2048)
    this.length = 0
  }
  process(inputs) {
    const channel = inputs[0] && inputs[0][0]
    if (channel) {
      if (this.length + channel.length > this.buffer.length) this.flush()
      this.buffer.set(channel, this.length)
      this.length += channel.length
    }
    return true
  }
  flush() {
    if (this.length === 0) return
    this.port.postMessage(this.buffer.slice(0, this.length))
    this.length = 0
  }
}
registerProcessor('${WORKLET_NAME}', VoiceCaptureProcessor)
`
// ScriptProcessorNode を使うときのバッファ長（サンプル数）
const SCRIPT_PROCESSOR_BUFFER = 4096

/** このブラウザ・この URL でマイクを使えるか（HTTP や Safari の file:// では使えない）。 */
export function isMicrophoneSupported() {
  return Boolean(navigator.mediaDevices?.getUserMedia)
}

/** getUserMedia などの例外を、利用者向けの分かりやすい文言にする。 */
export function describeMicrophoneError(error) {
  const messages = {
    NotAllowedError: 'マイクの使用が許可されませんでした。アドレスバーの左側にあるアイコンから、マイクを許可してください。',
    NotFoundError: 'マイクが見つかりませんでした。入力デバイスを接続してください。',
    NotReadableError: 'マイクを他のアプリが使用中の可能性があります。他のアプリを閉じてから、もう一度お試しください。',
    OverconstrainedError: '選択したマイクが見つかりません。マイクを選び直してください。',
  }
  return messages[error?.name] || `マイクのアクセスに失敗しました: ${error?.message || '不明なエラー'}`
}

/**
 * 入力デバイス（マイク）の一覧を返す。
 * マイクを一度も許可していないと、ブラウザは ID の無い仮の項目しか返さないため、それは除く。
 * 「既定」の項目（deviceId: 'default'）は、画面側の「既定のマイク」と重なるので除く。
 * @returns {Promise<Array<{ deviceId: string, label: string }>>}
 */
export async function listMicrophones() {
  if (!navigator.mediaDevices?.enumerateDevices) return []
  const devices = await navigator.mediaDevices.enumerateDevices()
  return devices
    .filter(d => d.kind === 'audioinput' && d.deviceId && d.deviceId !== 'default')
    .map((d, i) => ({ deviceId: d.deviceId, label: d.label || `マイク ${i + 1}` }))
}

/**
 * 録音した PCM を受け取るノードを作る。AudioWorklet を優先し、だめなら ScriptProcessor に切り替える。
 * @returns {Promise<AudioNode>}
 */
async function createCaptureNode(audioContext, onChunk) {
  if (audioContext.audioWorklet && typeof AudioWorkletNode !== 'undefined') {
    const url = URL.createObjectURL(new Blob([WORKLET_SOURCE], { type: 'application/javascript' }))
    try {
      await audioContext.audioWorklet.addModule(url)
      const node = new AudioWorkletNode(audioContext, WORKLET_NAME, {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        // ステレオで入力されるマイクでも、片方のチャンネルだけを拾わないようモノラルに混ぜる
        // （ScriptProcessor は入力チャンネル数 1 を指定すると、仕様上同じ混ぜ方になる）
        channelCount: 1,
        channelCountMode: 'explicit',
        channelInterpretation: 'speakers',
      })
      node.port.onmessage = (e) => onChunk(e.data)
      return node
    } catch (e) {
      console.warn('AudioWorklet を使えないため ScriptProcessor で録音します:', e)
    } finally {
      URL.revokeObjectURL(url)
    }
  }
  const node = audioContext.createScriptProcessor(SCRIPT_PROCESSOR_BUFFER, 1, 1)
  // 入力バッファはブラウザが使い回すため、コピーしてから渡す
  node.onaudioprocess = (e) => onChunk(e.inputBuffer.getChannelData(0).slice())
  return node
}

/**
 * マイクから録音を始める。
 * ブラウザ標準のノイズ抑制・自動音量調整・エコー除去はオフにする。標準処理が入力を
 * 時間とともに変化させると、カウントダウン中に学習したノイズと実際のノイズが食い違い、
 * スペクトル減算が不安定になるため。
 *
 * @param {string} [deviceId] 使うマイク（空なら既定のマイク）
 * @returns {Promise<{ analyser: AnalyserNode, sampleRate: number, stop: () => { samples: Float32Array, sampleRate: number } }>}
 */
export async function startCapture(deviceId = '') {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      deviceId: deviceId ? { exact: deviceId } : undefined,
      channelCount: 1,
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
    },
  })

  const AudioContextClass = window.AudioContext || window.webkitAudioContext
  const audioContext = new AudioContextClass()
  const chunks = []
  let stopped = false

  // 途中で失敗したときもマイクと AudioContext を確実に解放する
  const release = () => {
    stream.getTracks().forEach(track => track.stop())
    if (audioContext.state !== 'closed') audioContext.close().catch(() => {})
  }

  try {
    const source = audioContext.createMediaStreamSource(stream)
    const analyser = audioContext.createAnalyser()
    analyser.fftSize = 256
    source.connect(analyser)

    const captureNode = await createCaptureNode(audioContext, (chunk) => {
      if (!stopped) chunks.push(chunk)
    })
    // 受け取りノードは出力先につながっていないと動かないブラウザがあるため、
    // 音量 0 で出力先へつなぐ（スピーカーからは鳴らさない）
    const mute = audioContext.createGain()
    mute.gain.value = 0
    source.connect(captureNode)
    captureNode.connect(mute)
    mute.connect(audioContext.destination)

    // 自動再生の制限で suspended のまま始まることがあるため、明示的に動かす
    if (audioContext.state === 'suspended') await audioContext.resume()

    return {
      analyser,
      sampleRate: audioContext.sampleRate,
      /** 録音を止めてマイクを解放し、録音した音声をまとめて返す。 */
      stop() {
        stopped = true
        release()
        const total = chunks.reduce((sum, c) => sum + c.length, 0)
        const samples = new Float32Array(total)
        let offset = 0
        for (const c of chunks) {
          samples.set(c, offset)
          offset += c.length
        }
        return { samples, sampleRate: audioContext.sampleRate }
      },
    }
  } catch (e) {
    release()
    throw e
  }
}
