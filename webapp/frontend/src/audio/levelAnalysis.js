/**
 * 入力レベルの解析と警告（#11）
 *
 * 録音した 1 テイクについて、声の大きさ・音割れ・周囲の雑音・発話の長さを調べ、
 * 録り直したほうがよい場合に利用者へ伝える警告を作る。
 */
import { LEVEL_THRESHOLDS } from './config.js'

// 20ms @ 16kHz。発話の大きさを測るフレーム長（サーバー側の無音判定と同じ）
const FRAME_SIZE = 320
// 背景ノイズより 10dB 以上大きいフレームを発話とみなす
const VOICED_ABOVE_NOISE = 10 ** (10 / 20)
// 発話の基準より 20dB 以上小さいフレームは、発話とみなさない
const VOICED_BELOW_SPEECH = 10 ** (-20 / 20)
// 背景ノイズから決めた閾値の上限（発話の基準より 12dB 下）。雑音が大きいと閾値が
// 発話の近くまで上がり、発話まで数えられずに「短すぎる」と誤って警告してしまうため
const VOICED_NOISE_CAP = 10 ** (-12 / 20)

/** 振幅を dBFS に変換する（0 は -200dB として扱う）。 */
export function toDb(amplitude) {
  return 20 * Math.log10(Math.max(amplitude, 1e-10))
}

/** 区間の RMS（実効値）を求める。 */
export function rms(samples) {
  if (!samples?.length) return 0
  let sum = 0
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i]
  return Math.sqrt(sum / samples.length)
}

/** フレームごとの RMS を並べた配列を返す。端数のサンプルは使わない。 */
function frameRmsList(samples) {
  const count = Math.floor(samples.length / FRAME_SIZE)
  const list = new Float64Array(count)
  for (let f = 0; f < count; f++) {
    list[f] = rms(samples.subarray(f * FRAME_SIZE, (f + 1) * FRAME_SIZE))
  }
  return list
}

/** 上位から数えた百分位の値（ratio=0.95 なら上位 5% の境目）を返す。 */
function percentile(values, ratio) {
  if (values.length === 0) return 0
  const sorted = Float64Array.from(values).sort()
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * ratio))]
}

/**
 * 区間内で音割れしたサンプルの割合を求める。
 * 16kHz へ変換すると波形がなまって音割れが分からなくなるため、録音したままの音声で数える。
 */
export function clippedRatio(samples, start = 0, end = samples.length) {
  if (end <= start) return 0
  let clipped = 0
  for (let i = start; i < end; i++) {
    if (Math.abs(samples[i]) >= LEVEL_THRESHOLDS.clipAmplitude) clipped++
  }
  return clipped / (end - start)
}

/**
 * 1 テイクのレベルを解析し、警告の一覧を作る。
 * @param {object} params
 * @param {Float32Array} params.speech 発話の区間（16kHz・ノイズ除去前）
 * @param {Float32Array} params.noise  カウントダウン中の無言の区間（16kHz）
 * @param {number} params.clipRatio    音割れしたサンプルの割合（clippedRatio() の結果）
 * @param {number} params.sampleRate   speech / noise のサンプリングレート
 */
export function analyzeLevels({ speech, noise, clipRatio, sampleRate }) {
  const frames = frameRmsList(speech)
  const speechLevel = percentile(frames, 0.95)
  const noiseLevel = rms(noise)

  const voicedThreshold = Math.max(
    speechLevel * VOICED_BELOW_SPEECH,
    Math.min(noiseLevel * VOICED_ABOVE_NOISE, speechLevel * VOICED_NOISE_CAP),
  )
  const voicedFrames = frames.filter(v => v > 0 && v >= voicedThreshold).length
  const voicedSec = (voicedFrames * FRAME_SIZE) / sampleRate

  const speechDb = toDb(speechLevel)
  const noiseDb = toDb(noiseLevel)
  const snrDb = speechDb - noiseDb

  const t = LEVEL_THRESHOLDS
  const warnings = []
  if (clipRatio > t.clipRatio) {
    warnings.push({
      code: 'clipping',
      message: '音割れしています。マイクから少し離れるか、マイクの入力音量を下げて録り直してください。',
    })
  }
  if (speechDb < t.quietSpeechDb) {
    warnings.push({
      code: 'quiet',
      message: '声が小さすぎます。マイクに近づくか、マイクの入力音量を上げて録り直してください。',
    })
  } else if (snrDb < t.minSnrDb) {
    // 声が小さいときは S/N 比も下がるので、先に「声が小さい」だけを伝える
    warnings.push({
      code: 'noisy',
      message: '周囲の雑音が大きめです。静かな場所で録り直すか、ノイズ除去を強めてください。',
    })
  }
  if (voicedSec < t.minVoicedSec) {
    warnings.push({
      code: 'short',
      message: `発話が短すぎます（${t.minVoicedSec}秒未満）。録り直しをおすすめします。`,
    })
  }

  return { speechDb, noiseDb, snrDb, voicedSec, clipRatio, warnings }
}
