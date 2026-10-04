/**
 * ノイズ学習型のスペクトル減算（#11）
 *
 * 録音開始時のカウントダウン中（無言の区間）から部屋のノイズのスペクトルを学習し、
 * 発話の音声からその成分を周波数ごとに差し引く。空調・PC のファンのような
 * 定常的なノイズに特に効く。
 *
 * 単純な引き算だとノイズの残りが「シュワシュワ」した音（ミュージカルノイズ）になるため、
 * 各周波数の S/N 比を前のフレームから滑らかに推定する decision-directed 法
 * （Ephraim–Malah）と、Wiener フィルタ型の利得を使っている。
 */
import { FFT } from './fft.js'

// 1 フレーム 512 サンプル（16kHz で 32ms）。音声の処理で一般的な長さ
const FRAME_SIZE = 512
// フレームを 1/4 ずつずらす（75% 重ね合わせ）。継ぎ目の音質劣化を抑える
const HOP_SIZE = FRAME_SIZE / 4
const BIN_COUNT = FRAME_SIZE / 2 + 1
// 前フレームの推定をどれだけ引き継ぐか。0.98 は decision-directed 法の定番値で、
// 大きいほどミュージカルノイズが減る代わりに、発話の立ち上がりへの追従が遅くなる
const PRIOR_SMOOTHING = 0.98
// 無音の区間でパワーが 0 になっても割り算で発散しないための下限
const POWER_EPSILON = 1e-12

// 分析と合成の両方に √ハン窓を掛ける（掛け合わせるとハン窓になり、重ね合わせで元に戻る）
const WINDOW = (() => {
  const w = new Float64Array(FRAME_SIZE)
  for (let i = 0; i < FRAME_SIZE; i++) {
    w[i] = Math.sqrt(0.5 - 0.5 * Math.cos((2 * Math.PI * i) / FRAME_SIZE))
  }
  return w
})()

// 窓を掛けて重ね合わせたときの振幅の倍率（75% 重ね合わせのハン窓では 2）。
// 定数を決め打ちせず、窓から計算して割り戻す
const OVERLAP_GAIN = (() => {
  let sum = 0
  for (let i = 0; i < FRAME_SIZE; i += HOP_SIZE) sum += WINDOW[i] ** 2
  return sum
})()

let sharedFft = null
function getFft() {
  // 表の作成は 1 回で済むよう使い回す
  if (!sharedFft) sharedFft = new FFT(FRAME_SIZE)
  return sharedFft
}

/** samples の pos から 1 フレームを窓掛けして FFT し、re / im に入れる。 */
function analyzeFrame(samples, pos, re, im) {
  for (let i = 0; i < FRAME_SIZE; i++) {
    re[i] = samples[pos + i] * WINDOW[i]
    im[i] = 0
  }
  getFft().transform(re, im)
}

/**
 * 無言の区間からノイズのパワースペクトル（周波数ごとの平均）を学習する。
 * @param {Float32Array} samples 無言の区間の音声
 * @returns {Float64Array|null} 学習できるだけの長さが無ければ null
 */
export function estimateNoiseProfile(samples) {
  if (!samples || samples.length < FRAME_SIZE) return null

  const re = new Float64Array(FRAME_SIZE)
  const im = new Float64Array(FRAME_SIZE)
  const profile = new Float64Array(BIN_COUNT)
  let frameCount = 0
  for (let pos = 0; pos + FRAME_SIZE <= samples.length; pos += HOP_SIZE) {
    analyzeFrame(samples, pos, re, im)
    for (let k = 0; k < BIN_COUNT; k++) profile[k] += re[k] * re[k] + im[k] * im[k]
    frameCount++
  }
  for (let k = 0; k < BIN_COUNT; k++) {
    profile[k] = Math.max(profile[k] / frameCount, POWER_EPSILON)
  }
  return profile
}

/**
 * 学習したノイズを差し引く。入力は書き換えず、同じ長さの新しい配列を返す。
 * @param {Float32Array} samples 発話の音声
 * @param {Float64Array} noiseProfile estimateNoiseProfile() の結果
 * @param {{ overSubtraction: number, floor: number }} strength config.js の強さの設定
 * @returns {Float32Array}
 */
export function reduceNoise(samples, noiseProfile, { overSubtraction, floor }) {
  // 先頭・末尾も 4 枚のフレームで重なるよう、前後を 0 で埋めてから処理する
  const pad = FRAME_SIZE - HOP_SIZE
  const frameCount = Math.ceil((samples.length + pad) / HOP_SIZE)
  const paddedLength = (frameCount - 1) * HOP_SIZE + FRAME_SIZE
  const input = new Float64Array(paddedLength)
  input.set(samples, pad)
  const output = new Float64Array(paddedLength)

  const fft = getFft()
  const re = new Float64Array(FRAME_SIZE)
  const im = new Float64Array(FRAME_SIZE)
  // 前フレームで推定した「ノイズ除去後のパワー / ノイズのパワー」（周波数ごと）
  const previousCleanSnr = new Float64Array(BIN_COUNT)

  for (let frame = 0; frame < frameCount; frame++) {
    const pos = frame * HOP_SIZE
    analyzeFrame(input, pos, re, im)

    for (let k = 0; k < BIN_COUNT; k++) {
      // 事後 S/N 比: 観測したパワーがノイズの何倍か
      const posteriorSnr = (re[k] * re[k] + im[k] * im[k]) / noiseProfile[k]
      const instantSnr = Math.max(posteriorSnr - 1, 0)
      // 事前 S/N 比: 前フレームの推定と今回の観測を滑らかにつなぐ（最初のフレームは観測のみ）
      const priorSnr = frame === 0
        ? instantSnr
        : PRIOR_SMOOTHING * previousCleanSnr[k] + (1 - PRIOR_SMOOTHING) * instantSnr
      // Wiener 型の利得。overSubtraction が大きいほど強く抑え、floor より小さくはしない
      const gain = Math.max(priorSnr / (priorSnr + overSubtraction), floor)
      previousCleanSnr[k] = gain * gain * posteriorSnr

      re[k] *= gain
      im[k] *= gain
      // 実数の信号なので、負の周波数側（共役の位置）にも同じ利得を掛ける
      if (k > 0 && k < FRAME_SIZE / 2) {
        re[FRAME_SIZE - k] *= gain
        im[FRAME_SIZE - k] *= gain
      }
    }

    fft.transform(re, im, true)
    for (let i = 0; i < FRAME_SIZE; i++) output[pos + i] += re[i] * WINDOW[i]
  }

  const result = new Float32Array(samples.length)
  for (let i = 0; i < samples.length; i++) result[i] = output[pad + i] / OVERLAP_GAIN
  return result
}
