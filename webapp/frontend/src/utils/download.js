/**
 * Blob をファイルとして保存させる（ブラウザのダウンロード）。
 * 設定画面（録音ツールのダウンロード）と録音ツール（収録データの保存）で共用する。
 * @param {Blob} blob
 * @param {string} fileName
 */
export function saveBlobAsFile(blob, fileName) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  link.remove()
  // クリック直後に解放するとダウンロードが始まらないブラウザがあるため、少し待つ
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}
