/**
 * 高速フーリエ変換（基数 2・反復型）（#11）
 *
 * スペクトル減算で使う。外部ライブラリに頼らず、録音ツールを単一 HTML のまま
 * 小さく保つために自前で実装している。サイズごとに表を作り直さないよう、
 * インスタンスを使い回す前提。
 */
export class FFT {
  /** @param {number} size 2 のべき乗 */
  constructor(size) {
    if (size < 2 || (size & (size - 1)) !== 0) {
      throw new Error(`FFT のサイズは 2 のべき乗にしてください: ${size}`)
    }
    this.size = size

    // ビット反転の並べ替え表
    const bits = Math.log2(size)
    this.reversed = new Uint32Array(size)
    for (let i = 0; i < size; i++) {
      let r = 0
      for (let b = 0; b < bits; b++) r |= ((i >> b) & 1) << (bits - 1 - b)
      this.reversed[i] = r
    }

    // 回転因子の表（cos / sin の半周期分）
    this.cos = new Float64Array(size / 2)
    this.sin = new Float64Array(size / 2)
    for (let i = 0; i < size / 2; i++) {
      this.cos[i] = Math.cos((2 * Math.PI * i) / size)
      this.sin[i] = Math.sin((2 * Math.PI * i) / size)
    }
  }

  /**
   * 実部 re・虚部 im をその場で変換する。
   * @param {Float64Array} re
   * @param {Float64Array} im
   * @param {boolean} inverse true なら逆変換（1/N の正規化込み）
   */
  transform(re, im, inverse = false) {
    const n = this.size

    for (let i = 0; i < n; i++) {
      const j = this.reversed[i]
      if (j > i) {
        let t = re[i]; re[i] = re[j]; re[j] = t
        t = im[i]; im[i] = im[j]; im[j] = t
      }
    }

    // 順変換は e^{-iθ}、逆変換は e^{+iθ} を掛ける
    const sign = inverse ? 1 : -1
    for (let len = 2; len <= n; len <<= 1) {
      const half = len >> 1
      const step = n / len
      for (let start = 0; start < n; start += len) {
        for (let k = 0; k < half; k++) {
          const wr = this.cos[k * step]
          const wi = sign * this.sin[k * step]
          const a = start + k
          const b = a + half
          const tr = re[b] * wr - im[b] * wi
          const ti = re[b] * wi + im[b] * wr
          re[b] = re[a] - tr
          im[b] = im[a] - ti
          re[a] += tr
          im[a] += ti
        }
      }
    }

    if (inverse) {
      for (let i = 0; i < n; i++) {
        re[i] /= n
        im[i] /= n
      }
    }
  }
}
