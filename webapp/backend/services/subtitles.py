"""字幕（SRT）を作る（#97）。

以前は 1 シーンを 1 つの字幕にしていた。実データでは 1 つの字幕が平均 193 字・
36 秒（最長 555 字・101 秒）画面に出続け、字幕として読めなかった。

ここでは次のように作る。
  - 1 字幕 = 1 文。長い文（MAX_CUE_CHARS 超）は、真ん中に近い読点で分ける
  - 時刻はシーンの音声の範囲の中で、文字数に比例して割り振る
  - ナレーションの区切り（#3）の秒数があれば、区切りの境目はその秒数に合わせる
  - 間の指定（［間］）は、その位置の無音として時間を空ける
  - 対話レイアウトは、台詞 1 行を 1 字幕にする
"""
import json
import re

from services.composition import narration_segment_starts
from services.design_tokens import normalize_narration_speed
from services.reading import PAUSE_RE, pause_seconds, strip_markup
from services.scene_tts import narration_segments

# 1 字幕の文字数の目安。フル HD の字幕 2 行ぶん
MAX_CUE_CHARS = 40
# 文の終わり（ここで字幕を分ける）と、長い文を分けてよい位置
_SENTENCE_END_RE = re.compile(r"(?<=[。．！？!?])|\n")
_CLAUSE_END_RE = re.compile(r"(?<=[、，,])")

# 字幕 1 つ = (開始秒, 終了秒, 文字列)
Cue = tuple[float, float, str]


def split_sentences(text: str) -> list[str]:
    """表記（書式を外したもの）を字幕の単位に分ける。"""
    out: list[str] = []
    for sentence in _SENTENCE_END_RE.split(text):
        sentence = sentence.strip()
        if sentence:
            out.extend(_split_long(sentence))
    return out


def _split_long(sentence: str) -> list[str]:
    """長い文を、真ん中に近い読点で 2 つに分ける（まだ長ければ繰り返す）。"""
    if len(sentence) <= MAX_CUE_CHARS:
        return [sentence]
    bounds = [m.end() for m in _CLAUSE_END_RE.finditer(sentence) if 0 < m.end() < len(sentence)]
    if not bounds:
        # 読点が無ければ、字数で切る
        cut = len(sentence) // 2
    else:
        cut = min(bounds, key=lambda b: abs(b - len(sentence) / 2))
    return _split_long(sentence[:cut].strip()) + _split_long(sentence[cut:].strip())


def _pieces(text: str) -> list[str | float]:
    """本文（書式つき）を、字幕の文字列と間（秒）の並びにする。"""
    pieces: list[str | float] = []
    cursor = 0
    for m in PAUSE_RE.finditer(text):
        pieces.extend(split_sentences(strip_markup(text[cursor:m.start()])))
        pieces.append(pause_seconds(m))
        cursor = m.end()
    pieces.extend(split_sentences(strip_markup(text[cursor:])))
    return pieces


def _spread(pieces: list[str | float], start: float, end: float, speed: float) -> list[Cue]:
    """[start, end] の中で、文字数に比例して字幕の時刻を割り振る。

    間は合成の後に話速が掛かるので、話速で割った秒数ぶん空ける。
    """
    texts = [p for p in pieces if isinstance(p, str)]
    if not texts or end <= start:
        return []
    pauses = sum(p for p in pieces if not isinstance(p, str)) / speed
    span = end - start
    # 間が長すぎて話す時間が無くなるときは、間を詰める（字幕が 0 秒にならないように）
    speech = max(span - pauses, span * 0.3)
    pause_scale = (span - speech) / pauses if pauses else 0.0
    per_char = speech / sum(len(t) for t in texts)

    cues: list[Cue] = []
    t = start
    for p in pieces:
        if isinstance(p, str):
            cues.append((t, t + len(p) * per_char, p))
            t += len(p) * per_char
        else:
            t += p / speed * pause_scale
    return cues


def scene_cues(scene, style=None) -> list[Cue]:
    """1 シーンぶんの字幕。時刻は動画の先頭からの秒数。

    シーンの音声の範囲（data_start から音声の長さぶん）の中に並べる。
    """
    if scene.data_start is None:
        return []
    start = scene.data_start
    duration = scene.narration_audio_duration or 0.0
    speed = normalize_narration_speed(getattr(style, "narration_speed", None)) if style else 1.0

    if scene.layout_type == "chat_dialog" and scene.slide_content_json:
        try:
            lines = json.loads(scene.slide_content_json).get("lines") or []
        except (ValueError, AttributeError):
            lines = []
        text = "\n".join(str(line.get("text") or "") for line in lines if isinstance(line, dict))
        return _spread(_pieces(text), start, start + duration, speed)

    texts = narration_segments(scene)
    starts = narration_segment_starts(scene, style)
    if texts and starts and len(starts) == len(texts):
        # 区切りの境目を、音声合成で測った秒数に合わせる
        bounds = [min(s, duration) for s in starts] + [duration]
        cues: list[Cue] = []
        for text, a, b in zip(texts, bounds, bounds[1:]):
            cues.extend(_spread(_pieces(text), start + a, start + b, speed))
        return cues
    return _spread(_pieces(scene.narration_text or ""), start, start + duration, speed)


def _srt_time(seconds: float) -> str:
    """秒数を SRT の時刻（HH:MM:SS,mmm）にする。

    ミリ秒に丸めてから分解する。秒の端数だけを丸めると、1.9996 秒が
    「00:00:01,1000」のような不正な時刻になっていた。
    """
    total_ms = int(round(max(seconds, 0.0) * 1000))
    h, rest = divmod(total_ms, 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, ms = divmod(rest, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(scenes, style=None) -> str:
    """シーンの並び（音声の時刻が決まっているもの）から SRT の本文を作る。番号は連番。"""
    cues = [cue for scene in scenes for cue in scene_cues(scene, style)]
    blocks = [
        f"{n}\n{_srt_time(a)} --> {_srt_time(b)}\n{text}\n"
        for n, (a, b, text) in enumerate(cues, start=1)
    ]
    return "\n".join(blocks)
