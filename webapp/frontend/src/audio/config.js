/**
 * 録音・ノイズ処理の共通設定（#11）
 *
 * 設定画面の「音声収集セッション」と、ローカル録音ツール（#12）の両方が使う。
 * ここを変えると両方の動作が同じように変わる。
 */

// 書き出す音声のサンプリングレート。Qwen3-TTS の参照音声（16kHz）に合わせる
export const TARGET_SAMPLE_RATE = 16000

// ─── 端の自動カット ──────────────────────────────────────────
// 録音ボタンを押してから発話を受け付けるまでのカウントダウン（秒）。
// この間は無言で待ってもらい、部屋のノイズを学習する
export const COUNTDOWN_SEC = 3
// ノイズの学習はここから始める。ボタン操作直後はクリック音を含むため使わない
export const NOISE_LEARN_START_SEC = 0.5
// 停止ボタンのクリック音を含む末尾を、この秒数だけ捨てる
export const TAIL_CUT_SEC = 0.3
// 録音の上限（秒）。止め忘れでメモリを使い続けないよう、超えたら自動で止める
export const MAX_RECORDING_SEC = 90

// ─── ノイズ除去（スペクトル減算）の強さ ────────────────────────
// overSubtraction … 推定したノイズをどれだけ強めに差し引くか（大きいほど強い）
// floor           … 1 つの周波数成分を最大でどこまで小さくするか（振幅の比）。
//                   0 に近いほど強く消えるが、声がこもったり「シュワシュワ」した音が出やすい
export const NOISE_REDUCTION_LEVELS = [
  { value: 'off', label: 'オフ' },
  { value: 'low', label: '弱', overSubtraction: 1.0, floor: 0.3 },
  { value: 'medium', label: '中', overSubtraction: 2.0, floor: 0.15 },
  { value: 'high', label: '強', overSubtraction: 3.0, floor: 0.07 },
]
export const DEFAULT_NOISE_REDUCTION = 'medium'

/** 強さの値（'medium' など）から設定を引く。見つからなければ既定値を返す。 */
export function findNoiseReductionLevel(value) {
  return NOISE_REDUCTION_LEVELS.find(l => l.value === value)
    ?? NOISE_REDUCTION_LEVELS.find(l => l.value === DEFAULT_NOISE_REDUCTION)
}

// ─── 入力レベルの警告 ────────────────────────────────────────
export const LEVEL_THRESHOLDS = {
  // 発話の大きさ（上位 5% のフレームの RMS）がこれ未満なら「声が小さい」(dBFS)
  quietSpeechDb: -36,
  // この振幅以上のサンプルを音割れとみなす
  clipAmplitude: 0.99,
  // 音割れしたサンプルの割合がこれを超えたら警告する
  clipRatio: 0.0005,
  // 発話と周囲の雑音の差がこれ未満なら「雑音が大きい」(dB)
  minSnrDb: 20,
  // 発話と判定できた長さがこれ未満なら「短すぎる」(秒)
  minVoicedSec: 1.0,
}
