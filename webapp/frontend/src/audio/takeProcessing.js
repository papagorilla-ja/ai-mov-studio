/**
 * 1 テイク分の後処理（#11）
 *
 * 録音したままの音声から、次の手順で「サーバーへ送る音声」を作る。
 *   1. 16kHz に変換する
 *   2. 端をカットする … 先頭のカウントダウン区間と、停止直前の末尾を捨てる
 *   3. カウントダウン中の無言区間からノイズを学習する
 *   4. ノイズを差し引く（強さは後から変えられるよう、元の音とは分けて持つ）
 *   5. 入力レベルを解析して警告を作る
 */
import {
  COUNTDOWN_SEC,
  NOISE_LEARN_START_SEC,
  TAIL_CUT_SEC,
  TARGET_SAMPLE_RATE,
  findNoiseReductionLevel,
} from './config.js'
import { analyzeLevels, clippedRatio } from './levelAnalysis.js'
import { estimateNoiseProfile, reduceNoise } from './noiseReduction.js'

// 発話の区間がこれより短ければ、録音されていないものとして扱う（秒）
const MIN_BODY_SEC = 0.2

/**
 * ブラウザの変換機能（OfflineAudioContext）でサンプリングレートを変える。
 * 自前で実装するより高品質で、折り返し雑音の対策も含まれている。
 */
async function resample(samples, fromRate, toRate) {
  if (fromRate === toRate) return samples.slice()
  const length = Math.ceil((samples.length * toRate) / fromRate)
  const context = new OfflineAudioContext(1, length, toRate)
  const buffer = context.createBuffer(1, samples.length, fromRate)
  buffer.copyToChannel(samples, 0)
  const source = context.createBufferSource()
  source.buffer = buffer
  source.connect(context.destination)
  source.start()
  const rendered = await context.startRendering()
  return rendered.getChannelData(0).slice()
}

/**
 * @typedef {object} Take
 * @property {Float32Array} original     発話の区間（16kHz・ノイズ除去前）
 * @property {Float64Array|null} noiseProfile 学習したノイズ（学習できなければ null）
 * @property {object} analysis           levelAnalysis.analyzeLevels() の結果
 * @property {number} durationSec        発話の区間の長さ
 */

/**
 * 録音したままの音声から 1 テイクを作る。
 * @param {{ samples: Float32Array, sampleRate: number }} recorded capture.stop() の結果
 * @returns {Promise<Take|null>} 発話の区間が無ければ null
 */
export async function buildTake({ samples, sampleRate }) {
  const bodyStart = Math.round(COUNTDOWN_SEC * sampleRate)
  const bodyEnd = samples.length - Math.round(TAIL_CUT_SEC * sampleRate)
  if (bodyEnd - bodyStart < MIN_BODY_SEC * sampleRate) return null

  // 音割れは、16kHz に変換する前の録音したままの音声で数える
  const clipRatio = clippedRatio(samples, bodyStart, bodyEnd)

  const resampled = await resample(samples, sampleRate, TARGET_SAMPLE_RATE)
  const at = (sec) => Math.round(sec * TARGET_SAMPLE_RATE)
  const noise = resampled.subarray(at(NOISE_LEARN_START_SEC), at(COUNTDOWN_SEC))
  const original = resampled.slice(at(COUNTDOWN_SEC), resampled.length - at(TAIL_CUT_SEC))

  return {
    original,
    noiseProfile: estimateNoiseProfile(noise),
    analysis: analyzeLevels({ speech: original, noise, clipRatio, sampleRate: TARGET_SAMPLE_RATE }),
    durationSec: original.length / TARGET_SAMPLE_RATE,
  }
}

/**
 * テイクにノイズ除去を掛けた音声を返す。オフのとき、またはノイズを学習できなかったときは元の音を返す。
 * @param {Take} take
 * @param {string} levelValue 強さ（'off' / 'low' / 'medium' / 'high'）
 * @returns {Float32Array}
 */
export function applyNoiseReduction(take, levelValue) {
  const level = findNoiseReductionLevel(levelValue)
  if (level.value === 'off' || !take.noiseProfile) return take.original
  return reduceNoise(take.original, take.noiseProfile, level)
}
