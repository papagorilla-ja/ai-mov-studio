/**
 * 録音ツールの HTML に埋め込むデータ（読み上げ文など）（#12）
 *
 * 録音ツールはサーバーと通信せずに動くため、設定画面からダウンロードするときに
 * 読み上げ文（提示項目）などを HTML の中へ書き込む。
 *
 * 埋め込み先は tools/voice-recorder.html の次の要素:
 *   <script id="voice-recorder-data" type="application/json">__VOICE_RECORDER_DATA__</script>
 */

const DATA_ELEMENT_ID = 'voice-recorder-data'
const DATA_PLACEHOLDER = '__VOICE_RECORDER_DATA__'
// 置き換えは「データ用の script 要素」全体に一致させて行う。
// ツールの JS も同じ HTML に埋め込まれており、置き換え用の文字列だけで探すと、
// 先に現れる JS 側を書き換えてしまうため。
const DATA_ELEMENT_PATTERN = new RegExp(
  `(<script id="${DATA_ELEMENT_ID}" type="application/json">)${DATA_PLACEHOLDER}(</script>)`,
)

/**
 * 設定画面用: ツールの HTML にデータを埋め込んだ HTML を返す。
 * @param {string} html ビルド済みの録音ツール（dist/tools/voice-recorder.html）
 * @param {object} data 埋め込むデータ
 */
export function embedRecorderData(html, data) {
  if (!DATA_ELEMENT_PATTERN.test(html)) {
    throw new Error('録音ツールのファイルに、データの埋め込み先が見つかりません。')
  }
  // "<" を < に置き換え、データに "</script>" が含まれても HTML の構造が壊れないようにする
  const json = JSON.stringify(data).replace(/</g, '\\u003c')
  // 置き換え後の文字列に "$" が含まれても特別扱いされないよう、関数で返す
  return html.replace(DATA_ELEMENT_PATTERN, (_, open, close) => `${open}${json}${close}`)
}

/**
 * 録音ツール用: 埋め込まれたデータを読む。
 * 埋め込まれていない（置き換え前の文字列のまま）・壊れているときは null を返す。
 */
export function readRecorderData() {
  const text = document.getElementById(DATA_ELEMENT_ID)?.textContent ?? ''
  try {
    const data = JSON.parse(text)
    return data && typeof data === 'object' && data.items ? data : null
  } catch {
    return null
  }
}
