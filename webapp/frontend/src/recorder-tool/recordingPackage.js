/**
 * 収録パッケージ（.zip）の作成（#12）
 *
 * 録音ツールで録ったテイクを、設定画面の「収録データを取り込む」で読める形にまとめる。
 *   manifest.json … 形式・バージョン・名前・収録モード・各テイクの情報
 *   takes/NN.wav  … ノイズ除去後の音声（16kHz・モノラル・16bit）
 *
 * サーバー側の読み込みは webapp/backend/services/recording_package.py。
 * 形式を変えるときは、両方を合わせて PACKAGE_VERSION を上げること。
 */
import { TARGET_SAMPLE_RATE } from '@/audio/config.js'
import { encodeWav } from '@/audio/wav.js'
import { createZip } from './zip.js'

export const PACKAGE_FORMAT = 'ai-mov-studio/voice-recording'
export const PACKAGE_VERSION = 1

// Windows でファイル名に使えない文字（と制御文字）
const UNSAFE_FILE_CHARS = /[\\/:*?"<>|\u0000-\u001f]/g
const MAX_NAME_IN_FILE = 40

/**
 * 収録パッケージを作る。
 * @param {object} params
 * @param {string} params.name 収録音声の名前
 * @param {string} params.mode 収録モード
 * @param {Array<{ prompt: string, instruction: string }>} params.items 提示項目
 * @param {Array<{ take: object, processed: Float32Array, noiseReduction: string }>} params.takes
 *   項目と同じ順のテイク（useVoiceTakeRecorder の exportTake() の結果）
 * @param {Date} [params.createdAt]
 * @returns {Blob}
 */
export function buildRecordingPackage({ name, mode, items, takes, createdAt = new Date() }) {
  if (takes.length !== items.length || takes.some(t => !t)) {
    throw new Error('録音していない項目があります。')
  }

  const takeFiles = []
  const manifestTakes = items.map((item, i) => {
    const saved = takes[i]
    const file = `takes/${String(i + 1).padStart(2, '0')}.wav`
    takeFiles.push({ name: file, data: encodeWav(saved.processed, TARGET_SAMPLE_RATE) })
    return {
      index: i + 1,
      file,
      prompt: item.prompt,
      instruction: item.instruction,
      duration_sec: Math.round(saved.take.durationSec * 100) / 100,
      noise_reduction: saved.noiseReduction,
      // 録音時に出ていた警告（声が小さい・音割れなど）。後から品質を確かめるための記録
      warnings: saved.take.analysis.warnings.map(w => w.code),
    }
  })

  const manifest = {
    format: PACKAGE_FORMAT,
    version: PACKAGE_VERSION,
    name,
    mode,
    created_at: createdAt.toISOString(),
    sample_rate: TARGET_SAMPLE_RATE,
    takes: manifestTakes,
  }
  const manifestFile = {
    name: 'manifest.json',
    data: new TextEncoder().encode(JSON.stringify(manifest, null, 2)),
  }
  return createZip([manifestFile, ...takeFiles], createdAt)
}

/** 保存するファイル名を作る（例: 収録データ_山田さんの声_20261004-1530.zip）。 */
export function packageFileName(name, date = new Date()) {
  const safeName = name.replace(UNSAFE_FILE_CHARS, '').trim().slice(0, MAX_NAME_IN_FILE) || '音声'
  const pad = (n) => String(n).padStart(2, '0')
  const stamp = `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}`
  return `収録データ_${safeName}_${stamp}.zip`
}
