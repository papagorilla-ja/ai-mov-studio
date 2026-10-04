/**
 * 無圧縮の zip ファイルを作る（#12）
 *
 * 収録パッケージ（manifest.json と WAV）を 1 つのファイルにまとめるために使う。
 * WAV はほとんど圧縮できないため、圧縮はせず「格納（stored）」だけを行う。
 * 外部ライブラリに頼らず、録音ツールを単一 HTML のまま小さく保つために自前で実装している。
 *
 * 形式は PKWARE の APPNOTE に従う（ZIP64 は使わない。1 ファイル 4GB 未満の前提）。
 */

const LOCAL_HEADER_SIZE = 30
const CENTRAL_HEADER_SIZE = 46
const END_RECORD_SIZE = 22
const VERSION = 20            // 展開に必要なバージョン（2.0）
const UTF8_FLAG = 0x0800      // ファイル名を UTF-8 で書いたことを示す

// CRC-32 の表（多項式 0xEDB88320）
const CRC_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    table[n] = c >>> 0
  }
  return table
})()

/** バイト列の CRC-32 を求める。 */
export function crc32(bytes) {
  let crc = 0xffffffff
  for (let i = 0; i < bytes.length; i++) crc = CRC_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8)
  return (crc ^ 0xffffffff) >>> 0
}

/** 日時を MS-DOS 形式（zip のヘッダに書く形）にする。 */
function toDosDateTime(date) {
  const time = (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2)
  const day = ((date.getFullYear() - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate()
  return { time, day }
}

/**
 * zip を作る。
 * @param {Array<{ name: string, data: Uint8Array }>} files 格納するファイル（name は "takes/01.wav" のような相対パス）
 * @param {Date} [date] ファイルの更新日時
 * @returns {Blob}
 */
export function createZip(files, date = new Date()) {
  const encoder = new TextEncoder()
  const { time, day } = toDosDateTime(date)
  const parts = []         // 書き出す順のバイト列（ローカルヘッダ + 中身）
  const centralParts = []  // 中央ディレクトリ
  let offset = 0

  for (const file of files) {
    const name = encoder.encode(file.name)
    const crc = crc32(file.data)
    const size = file.data.length

    const local = new DataView(new ArrayBuffer(LOCAL_HEADER_SIZE))
    local.setUint32(0, 0x04034b50, true)   // ローカルファイルヘッダの印
    local.setUint16(4, VERSION, true)
    local.setUint16(6, UTF8_FLAG, true)
    local.setUint16(8, 0, true)            // 圧縮方式: 格納
    local.setUint16(10, time, true)
    local.setUint16(12, day, true)
    local.setUint32(14, crc, true)
    local.setUint32(18, size, true)        // 圧縮後の大きさ（格納なので同じ）
    local.setUint32(22, size, true)        // 元の大きさ
    local.setUint16(26, name.length, true)
    local.setUint16(28, 0, true)           // 拡張フィールドの長さ
    parts.push(new Uint8Array(local.buffer), name, file.data)

    const central = new DataView(new ArrayBuffer(CENTRAL_HEADER_SIZE))
    central.setUint32(0, 0x02014b50, true) // 中央ディレクトリの印
    central.setUint16(4, VERSION, true)    // 作成したバージョン
    central.setUint16(6, VERSION, true)    // 展開に必要なバージョン
    central.setUint16(8, UTF8_FLAG, true)
    central.setUint16(10, 0, true)
    central.setUint16(12, time, true)
    central.setUint16(14, day, true)
    central.setUint32(16, crc, true)
    central.setUint32(20, size, true)
    central.setUint32(24, size, true)
    central.setUint16(28, name.length, true)
    // 30〜41: 拡張フィールド・コメントの長さ、ディスク番号、属性（すべて 0）
    central.setUint32(42, offset, true)    // ローカルヘッダの位置
    centralParts.push(new Uint8Array(central.buffer), name)

    offset += LOCAL_HEADER_SIZE + name.length + size
  }

  const centralSize = centralParts.reduce((sum, p) => sum + p.length, 0)
  const end = new DataView(new ArrayBuffer(END_RECORD_SIZE))
  end.setUint32(0, 0x06054b50, true)       // 中央ディレクトリ終端の印
  end.setUint16(8, files.length, true)     // このディスクのエントリ数
  end.setUint16(10, files.length, true)    // 全エントリ数
  end.setUint32(12, centralSize, true)
  end.setUint32(16, offset, true)          // 中央ディレクトリの位置

  return new Blob([...parts, ...centralParts, new Uint8Array(end.buffer)], { type: 'application/zip' })
}
