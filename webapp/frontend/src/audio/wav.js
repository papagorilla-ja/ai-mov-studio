/**
 * WAV 形式への変換（#11）
 *
 * モノラル・16bit PCM の WAV を作る。サーバーへの送信と、録音ツールの
 * 収録パッケージ（zip）の両方で使う。
 */

const HEADER_SIZE = 44
const BYTES_PER_SAMPLE = 2

function writeAscii(view, offset, text) {
  for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i))
}

/**
 * Float32 の音声（-1〜1）を WAV のバイト列にする。範囲外の値は丸める。
 * @param {Float32Array} samples
 * @param {number} sampleRate
 * @returns {Uint8Array}
 */
export function encodeWav(samples, sampleRate) {
  const dataSize = samples.length * BYTES_PER_SAMPLE
  const buffer = new ArrayBuffer(HEADER_SIZE + dataSize)
  const view = new DataView(buffer)

  writeAscii(view, 0, 'RIFF')
  view.setUint32(4, HEADER_SIZE - 8 + dataSize, true)
  writeAscii(view, 8, 'WAVE')
  writeAscii(view, 12, 'fmt ')
  view.setUint32(16, 16, true)                              // fmt チャンクの大きさ
  view.setUint16(20, 1, true)                               // 形式: リニア PCM
  view.setUint16(22, 1, true)                               // チャンネル数: モノラル
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * BYTES_PER_SAMPLE, true)   // 1 秒あたりのバイト数
  view.setUint16(32, BYTES_PER_SAMPLE, true)                // 1 サンプルのバイト数
  view.setUint16(34, 16, true)                              // ビット深度
  writeAscii(view, 36, 'data')
  view.setUint32(40, dataSize, true)

  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(HEADER_SIZE + i * BYTES_PER_SAMPLE, Math.round(s < 0 ? s * 0x8000 : s * 0x7fff), true)
  }
  return new Uint8Array(buffer)
}

/** WAV の Blob を作る（再生用の URL やアップロードに使う）。 */
export function encodeWavBlob(samples, sampleRate) {
  return new Blob([encodeWav(samples, sampleRate)], { type: 'audio/wav' })
}
