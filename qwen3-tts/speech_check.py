"""合成した音声の中身を、文字起こしで本文と照合する（#57）。

■ なぜ要るか
server.py の judge_chunk は音声の「長さ」しか見ていない。長さが大きく外れる崩れ
（EOS が出ずに上限まで生成する等）は拾えるが、次のような崩れは素通りする。

  「母親リリーの愛が守り続けたおかげで、…」（約 60 字、想定 10 秒）
  → 実際は 16 秒。途中の 11 秒が「フフフフ…」「彼は誇らしゼラし」
    「彼は誇らしゼニ」のような雑音と言い直しだった。
    長さは基準（想定の 1.7 倍＋2 秒 = 19.6 秒）の内側なので ok と判定されていた。

そこで、長さの判定を通ったチャンクをローカルの faster-whisper で文字起こしし、
本文と比べる。外部サービスには何も送らない。

■ 比べ方
漢字のまま比べると、音としては正しくても書き分けで一致しない
（例: 「賢者の石」を whisper が「検査の意思」と書く）。
そのため両方を**ひらがなに直してから**比べる。

  similarity   … 本文と文字起こしの一致度（difflib の ratio、0〜1）
  length_ratio … 文字起こしの長さ ÷ 本文の長さ。繰り返しや雑音の言葉化で大きくなる

加えて、本文の仮名の数を音声の長さで割った「読み上げの速さ」も見る。
いずれかが基準を外れたら「garbled」とする。基準値と、なぜ速さが要るかは
MIN_KANA_PER_SEC の上のコメントを参照。

■ 資源
whisper は CPU（int8）で動かす。TTS 本体が MPS を使うので、同じメモリを取り合わない。
base モデルは約 140MB。初回の照合のときに読み込む。
"""
import logging
import os
import re
import threading
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

import numpy as np

logger = logging.getLogger("qwen3-tts")

# 照合を使うか。問題が起きたときに 0 で切れるようにしておく。
ASR_CHECK_ENABLED = os.environ.get("TTS_ASR_CHECK", "1") != "0"
ASR_MODEL_SIZE = os.environ.get("TTS_ASR_MODEL", "base")
# ── 判定の基準（2026-09-27 に実データで決めた） ──────────────
# 正常な音声 48 チャンク（既定の話者、実際のナレーションから文単位で合成）と、
# 崩れた実例 1 件・人工の崩れ（繰り返し 6・打ち切り 6）で測った。
#
#                 正常 48 件            崩れた実例（シーン 8 の最後）
#   仮名/秒       最小 5.77・中央 7.23   4.32
#   一致度        最小 0.74             0.77
#   長さの比      0.82〜1.17            1.10
#
# **一致度だけでは見分けられない。** whisper は雑音をほとんど文字にしない
# （「ヒッヒッ」程度）ので、崩れた音声でも聞き取れた言葉は本文とよく一致する。
# 決め手になったのは読み上げの速さで、崩れた部分のぶん音声が間延びする。
# 速さは本文を仮名に直して数える。漢字の多い少ないで文字数あたりの
# 音の長さが変わるため、漢字交じりの文字数（judge_chunk の方式）より正確に測れる。
#
# 読み上げの速さの下限（仮名/秒）。等倍の音声で測る（話速は合成後に掛ける）。
# 正常の最小 5.77 に対して余裕を取る。声を複製した話者で地声が遅い場合に
# 誤検知しうるが、その場合も引き直しと警告になるだけで、合成は止まらない。
MIN_KANA_PER_SEC = float(os.environ.get("TTS_ASR_MIN_KANA_PER_SEC", "5.0"))
# 一致度の下限。別の言葉になってしまった音声を拾う（正常の最小 0.74）。
MIN_SIMILARITY = float(os.environ.get("TTS_ASR_MIN_SIMILARITY", "0.6"))
# 文字起こしの長さの比の上限と下限。
# 上限は繰り返し（2 回読むと約 2.0）を、下限は読み落とし（途中で切れると 0.3〜0.5）を拾う。
MAX_LENGTH_RATIO = float(os.environ.get("TTS_ASR_MAX_LENGTH_RATIO", "1.4"))
MIN_LENGTH_RATIO = float(os.environ.get("TTS_ASR_MIN_LENGTH_RATIO", "0.6"))
# これより短い本文は照合しない。数文字だと whisper の誤りが一致度を大きく動かし、
# 正常な音声まで崩れ扱いになる。短いチャンクは崩れても被害（秒数）が小さい。
MIN_CHECK_CHARS = int(os.environ.get("TTS_ASR_MIN_CHARS", "8"))

WHISPER_SAMPLE_RATE = 16000

_model = None
_model_lock = threading.Lock()      # 読み込みの排他
_transcribe_lock = threading.Lock()  # 推論の排他（ctranslate2 のモデルを同時に使わない）
_kakasi = None


@dataclass(frozen=True)
class SpeechCheck:
    verdict: str            # "ok" | "garbled" | "skipped"
    similarity: float
    length_ratio: float
    kana_per_sec: float
    heard: str              # 文字起こしの結果（ログ用）
    reason: str = ""        # garbled の理由（ログ用）

    def summary(self) -> str:
        return (f"一致度={self.similarity:.2f} 長さの比={self.length_ratio:.2f} "
                f"速さ={self.kana_per_sec:.2f}仮名/秒")


_SKIPPED = SpeechCheck("skipped", 1.0, 1.0, 0.0, "")


def _get_model():
    """whisper を初回だけ読み込む。読み込めなければ None（照合せずに続行）。"""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            try:
                from faster_whisper import WhisperModel
                _model = WhisperModel(ASR_MODEL_SIZE, device="cpu", compute_type="int8")
                logger.info(f"音声の照合用に whisper ({ASR_MODEL_SIZE}) を読み込みました")
            except Exception as e:  # noqa: BLE001
                # 照合は品質の保険であって、合成そのものではない。
                # 読み込めなくても合成は止めず、照合なしで続ける。
                logger.warning(f"whisper を読み込めないため、音声の照合を行いません: {e}")
                _model = False
    return _model or None


def to_kana(text: str) -> str:
    """比較用に、ひらがなと数字・英字だけの列に直す。

    句読点・記号・空白・長音符は捨てる。長音は whisper と pykakasi で
    「ー」と母音の書き分けが揺れるため、比べる対象から外す。
    小書きの仮名も普通の仮名に寄せる（「ゃ」と「や」の揺れを吸収する）。
    """
    global _kakasi
    if _kakasi is None:
        import pykakasi
        _kakasi = pykakasi.kakasi()
    t = unicodedata.normalize("NFKC", text or "")
    hira = "".join(part["hira"] for part in _kakasi.convert(t))
    hira = hira.translate(_SMALL_TO_LARGE).lower()
    return re.sub(r"[^ぁ-ゖa-z0-9]", "", hira)


_SMALL_TO_LARGE = str.maketrans("ぁぃぅぇぉっゃゅょゎゕゖ", "あいうえおつやゆよわかけ")


def _to_whisper_input(audio: np.ndarray, sr: int) -> np.ndarray:
    """whisper が受け取る 16kHz の float32 に直す。"""
    audio = np.asarray(audio, dtype=np.float32)
    if sr == WHISPER_SAMPLE_RATE:
        return audio
    # 線形補間で十分。音声認識の精度に効くほどの差は出ない。
    n = int(round(len(audio) * WHISPER_SAMPLE_RATE / sr))
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def transcribe(audio: np.ndarray, sr: int) -> str | None:
    """音声を文字起こしする。whisper が使えなければ None。"""
    model = _get_model()
    if model is None:
        return None
    with _transcribe_lock:
        segments, _ = model.transcribe(
            _to_whisper_input(audio, sr),
            language="ja",
            beam_size=1,
            # 前の区間の結果を次の手がかりにしない。有効にすると、雑音の区間で
            # 直前の文を繰り返す「幻聴」が起き、崩れていない音声まで長く書かれる。
            condition_on_previous_text=False,
            vad_filter=False,
            # タイムスタンプ付きにする。無しだと、雑音の区間を読み飛ばして
            # 「聞き取れた言葉だけ」を返し、崩れたチャンクでも本文と一致してしまう。
            without_timestamps=False,
        )
        # segments は遅延評価で、ここで実際に推論が走る。ロックの内側で消費する。
        return "".join(s.text for s in segments)


def compare(expected: str, heard: str) -> tuple[float, float]:
    """(一致度, 長さの比) を返す。"""
    a, b = to_kana(expected), to_kana(heard)
    if not a:
        return 1.0, 1.0
    similarity = SequenceMatcher(None, a, b, autojunk=False).ratio()
    return similarity, len(b) / len(a)


_warned_failure = False


def check_speech(text: str, audio: np.ndarray, sr: int) -> SpeechCheck:
    """チャンクの音声が本文どおりに読まれているかを判定する。

    audio は前後の無音を削った後のものを渡すこと。無音が残っていると
    読み上げの速さが実際より遅く測られる。

    照合は品質の保険であって、合成そのものではない。照合の中で何が起きても
    （依存ライブラリが無い、whisper が落ちた等）例外を外に出さず、
    「照合せず」として合成を続けさせる。
    """
    global _warned_failure
    try:
        return _check_speech(text, audio, sr)
    except Exception as e:  # noqa: BLE001
        if not _warned_failure:
            logger.warning(f"音声の照合に失敗したため、照合せずに続けます: {e!r}")
            _warned_failure = True
        return _SKIPPED


def preload() -> None:
    """起動時に whisper と仮名変換を読み込んでおく（最初の合成を遅らせないため）。"""
    if ASR_CHECK_ENABLED:
        check_speech("読み込みの確認です。これは照合の準備です。",
                     np.zeros(WHISPER_SAMPLE_RATE, dtype=np.float32), WHISPER_SAMPLE_RATE)


def _check_speech(text: str, audio: np.ndarray, sr: int) -> SpeechCheck:
    kana = to_kana(text)
    if not ASR_CHECK_ENABLED or len(kana) < MIN_CHECK_CHARS or len(audio) == 0:
        return _SKIPPED
    heard = transcribe(audio, sr)
    if heard is None:
        return _SKIPPED
    similarity, length_ratio = compare(text, heard)
    kana_per_sec = len(kana) / (len(audio) / sr)

    reasons = []
    if kana_per_sec < MIN_KANA_PER_SEC:
        reasons.append("読み上げが遅すぎる（雑音・言いよどみの疑い）")
    if length_ratio > MAX_LENGTH_RATIO:
        reasons.append("本文より長く読んでいる（繰り返しの疑い）")
    if length_ratio < MIN_LENGTH_RATIO:
        reasons.append("本文の一部しか読んでいない")
    if similarity < MIN_SIMILARITY:
        reasons.append("本文と違う言葉になっている")
    return SpeechCheck("garbled" if reasons else "ok", similarity, length_ratio,
                       kana_per_sec, heard, " / ".join(reasons))
