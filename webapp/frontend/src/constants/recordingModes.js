/**
 * 収録モードの定義（#12）
 *
 * 設定画面の「音声収集セッション」と、ローカル録音ツールで共用する。
 * value はサーバー側の services/voice_corpus.py の SUPPORTED_MODES と一致させること。
 */
export const RECORDING_MODES = [
  {
    value: 'script',
    label: '台本読み上げ',
    description: '表示された文をそのまま読み上げます。最も安定した参照音声が得られます。',
  },
  {
    value: 'chat',
    label: 'チャット対話',
    description: '画面の質問に声で自由に回答します。自然な抑揚が録れ、ナレーション向きの声質になります。',
  },
  {
    value: 'emotion',
    label: '感情・トーン指定',
    description: '指定されたトーンで読み上げます。声の幅を収集でき、動画の雰囲気に合わせやすくなります。',
  },
]

// 1 回の収録で選べる本数
export const SESSION_ITEM_COUNTS = [3, 5, 8, 10]
export const DEFAULT_SESSION_ITEM_COUNT = 5

/** モードの値（'script' など）から表示名を引く。未知の値はそのまま返す。 */
export function recordingModeLabel(value) {
  return RECORDING_MODES.find(m => m.value === value)?.label ?? value
}
