"""ナレーションの読みと間の制御（#60）。

Qwen3-TTS には読みやアクセントを直接指定する入力が無い。そのため
TTS に渡す前に文字列を書き換える。この書き換えを「読み上げ用テキスト」と呼ぶ。

■ 書き換えの材料（上ほど優先。人が決めたもの、狭い範囲のものを優先する）
  1. ルビ指定      ナレーション本文に ｜漢字《よみ》 と書く（青空文庫の書式）
  2. シーンの読み   本文に記号を入れずに「このシーンだけ」読みを変える（#73）
  3. プロジェクト辞書
  4. 全体辞書
  5. AI の読み     ローカル LLM が選んだ「読み間違えやすい語」の読み

■ 間の指定
  ［間］ で短い間（DEFAULT_PAUSE_SEC）、［間:1.5］ で秒数を指定する。
  読み上げ用テキストには残し、TTS に渡す直前（tts_service）でチャンクを切って
  無音に置き換える。

■ 本文はそのまま残す
  書き換えるのは TTS に渡す文字列だけで、ナレーション本文（narration_text）は
  変えない。本文はスライドとの対応づけ（区切り）やプロンプトの文脈にも使うため。
  それらの用途で書式が邪魔なときは strip_markup() で表記だけに戻す。
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass

# ｜ と 《》 は全角・半角のどちらでも受け付ける（NFKC で ｜ は | になる）。
RUBY_RE = re.compile(r"[｜|]([^｜|《》\n]+?)《([^《》\n]+?)》")
PAUSE_RE = re.compile(r"[［\[]間(?:\s*[:：]\s*(\d+(?:\.\d+)?))?\s*[］\]]")
# 間の既定と上限（秒）。上限は書き損じ（［間:100］）で動画が止まって見えるのを防ぐ。
DEFAULT_PAUSE_SEC = 0.5
MAX_PAUSE_SEC = 5.0

# 読みとして受け付ける文字（ひらがな・カタカナ・長音・中黒・空白）。
# AI の出力の検査に使う。辞書はユーザーが決めるので検査しない（英字の読みなども許す）。
_KANA_RE = re.compile(r"^[ぁ-ゖァ-ヺー・\s]+$")


def pause_seconds(match: re.Match) -> float:
    """間の書式から秒数を取り出す。範囲外は丸める。"""
    raw = match.group(1)
    sec = float(raw) if raw else DEFAULT_PAUSE_SEC
    return max(0.0, min(MAX_PAUSE_SEC, sec))


def total_pause_seconds(text: str | None) -> float:
    """本文に書かれた間の指定の合計秒数（尺の見積もり用）。"""
    return sum(pause_seconds(m) for m in PAUSE_RE.finditer(text or ""))


def strip_markup(text: str | None) -> str:
    """書式を外して、画面やプロンプトに出す表記に戻す（ルビは漢字、間は消す）。"""
    t = RUBY_RE.sub(lambda m: m.group(1), text or "")
    return PAUSE_RE.sub("", t)


def narration_hash(text: str | None) -> str:
    """AI の読みがどのナレーションに対するものかを見分けるためのハッシュ。"""
    return hashlib.md5((text or "").encode("utf-8")).hexdigest()


# ==========================================================================
# 読み上げ用テキストの組み立て
# ==========================================================================

@dataclass(frozen=True)
class Span:
    """読み上げ用テキストの中で、読みを書き換えた箇所。"""
    surface: str
    reading: str
    source: str       # "ruby" | "scene" | "project" | "global" | "ai"
    start: int        # 読み上げ用テキストの中の位置
    end: int
    src_start: int    # ナレーション本文の中の位置（ルビは書式全体）
    src_end: int


@dataclass(frozen=True)
class Reading:
    text: str
    spans: tuple[Span, ...]

    def to_dict(self, ai_checked: bool) -> dict:
        return {"text": self.text, "ai_checked": ai_checked,
                "spans": [asdict(s) for s in self.spans]}


@dataclass(frozen=True)
class Lexicon:
    """辞書と AI の読みをまとめたもの。優先順位を解決済みの状態で持つ。"""
    entries: dict[str, tuple[str, str]]   # 表記 → (読み, 出どころ)
    _by_first: dict[str, list[str]]       # 先頭の文字 → 表記（長い順）

    @classmethod
    def build(cls, *, scene: dict[str, str] | None = None,
              project: dict[str, str] | None = None,
              global_: dict[str, str] | None = None,
              ai: dict[str, str] | None = None) -> "Lexicon":
        entries: dict[str, tuple[str, str]] = {}
        # 優先度の低い順に入れて、高いもので上書きする
        for source, table in (("ai", ai), ("global", global_), ("project", project), ("scene", scene)):
            for surface, reading in (table or {}).items():
                if surface and reading:
                    entries[surface] = (reading, source)
        by_first: dict[str, list[str]] = {}
        for surface in entries:
            by_first.setdefault(surface[0], []).append(surface)
        for surfaces in by_first.values():
            # 長い語から当てる。「賢者の石」と「石」が両方あれば「賢者の石」が勝つ
            surfaces.sort(key=len, reverse=True)
        return cls(entries, by_first)

    def match(self, text: str, pos: int) -> str | None:
        for surface in self._by_first.get(text[pos], ()):
            if text.startswith(surface, pos):
                return surface
        return None


EMPTY_LEXICON = Lexicon.build()


class _Builder:
    """読み上げ用テキストを先頭から組み立てる。出力の位置と書き換え箇所を記録する。"""

    def __init__(self, lexicon: Lexicon):
        self.lexicon = lexicon
        self.parts: list[str] = []
        self.spans: list[Span] = []
        self.length = 0     # 出力済みの文字数（parts を毎回 join しないため）

    def emit(self, s: str) -> None:
        self.parts.append(s)
        self.length += len(s)

    def replace(self, surface: str, reading: str, source: str, src_start: int, src_end: int) -> None:
        self.spans.append(Span(surface, reading, source, self.length,
                               self.length + len(reading), src_start, src_end))
        self.emit(reading)

    def plain(self, text: str, start: int, end: int) -> None:
        """text[start:end] に辞書を当てて出力する。一致しない文字はそのまま出す。"""
        pos = plain_from = start
        while pos < end:
            surface = self.lexicon.match(text, pos) if self.lexicon.entries else None
            if surface and pos + len(surface) <= end:
                if plain_from < pos:
                    self.emit(text[plain_from:pos])
                reading, source = self.lexicon.entries[surface]
                self.replace(surface, reading, source, pos, pos + len(surface))
                pos = plain_from = pos + len(surface)
            else:
                pos += 1
        if plain_from < end:
            self.emit(text[plain_from:end])

    def result(self) -> Reading:
        return Reading("".join(self.parts), tuple(self.spans))


def build_reading(text: str | None, lexicon: Lexicon = EMPTY_LEXICON) -> Reading:
    """ナレーション本文から、TTS に渡す読み上げ用テキストを作る。

    ルビと間の書式は先に拾い、その内側には辞書を当てない
    （ルビで決めた読みを辞書が上書きしないように）。
    """
    text = text or ""
    b = _Builder(lexicon)
    # 書式（ルビ・間）の位置を並べる。書式の外側だけが辞書の対象
    marks = sorted(
        [(m.start(), m.end(), "ruby", m) for m in RUBY_RE.finditer(text)]
        + [(m.start(), m.end(), "pause", m) for m in PAUSE_RE.finditer(text)],
        key=lambda x: x[0],
    )
    cursor = 0
    for m_start, m_end, kind, m in marks:
        if m_start < cursor:
            continue    # 重なり（書き損じ）は先に出た方を採る
        b.plain(text, cursor, m_start)
        if kind == "ruby":
            b.replace(m.group(1), m.group(2), "ruby", m_start, m_end)
        else:
            # 間は書式のまま残す。tts_service がここでチャンクを切る
            b.emit(m.group(0))
        cursor = m_end
    b.plain(text, cursor, len(text))
    return b.result()


# ==========================================================================
# AI の読み（保存形式）
# ==========================================================================

def load_ai_readings(raw: str | None, narration: str | None) -> dict[str, str] | None:
    """保存済みの AI の読みを返す。今のナレーションに対するものでなければ None。"""
    try:
        data = json.loads(raw or "")
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("hash") != narration_hash(narration):
        return None
    return {r["surface"]: r["reading"] for r in data.get("readings") or []
            if isinstance(r, dict) and r.get("surface") and r.get("reading")}


def dump_ai_readings(readings: dict[str, str], narration: str | None) -> str:
    return json.dumps({
        "hash": narration_hash(narration),
        "readings": [{"surface": s, "reading": r} for s, r in readings.items()],
    }, ensure_ascii=False)


def clean_ai_readings(raw, narration: str) -> dict[str, str]:
    """LLM が返した読みを検査して、使えるものだけ残す。

    - 表記が本文（書式を外したもの）に実際にあること。無い語を足すと、
      意図しない場所が書き換わる恐れはないが、確認欄が無意味な語で埋まる
    - 読みが仮名だけであること（「けんじゃのいし（賢者の石）」のような混ぜ書きを弾く）
    - 表記がすでに仮名だけなら不要（書き換えても変わらない）
    """
    plain = strip_markup(narration)
    out: dict[str, str] = {}
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        surface = str(item.get("surface") or "").strip()
        reading = str(item.get("reading") or "").strip()
        if (not surface or not reading or len(surface) > 30 or surface not in plain
                or not _KANA_RE.match(reading) or _KANA_RE.match(surface)
                or surface == reading):
            continue
        out[surface] = reading
    return out


# ==========================================================================
# 書式の正規化と点検（#73）
#
# 書式は画面のボタンが入れるが、手で書くこともできる。手書きでは全角・半角が
# 混ざり、閉じ忘れも起きる。正しく読める書式は正しい形にそろえ、
# 読めないものは位置つきで知らせる（勝手に直すと意図と違う読みになりうる）。
# ==========================================================================

def _format_seconds(sec: float) -> str:
    return f"{sec:g}"


def normalize_markup(text: str | None) -> str:
    """正しく読める書式だけを、正しい形（｜漢字《よみ》・［間］・［間:1.5］）にそろえる。

    崩れた書式には触らない（inspect_markup が位置を知らせる）。
    間の秒数は丸めない。上限を超えた値は、点検で知らせたうえで合成時に丸める。
    """
    def ruby(m: re.Match) -> str:
        return f"｜{m.group(1)}《{m.group(2)}》"

    def pause(m: re.Match) -> str:
        raw = m.group(1)
        return "［間］" if raw is None else f"［間:{_format_seconds(float(raw))}］"

    return PAUSE_RE.sub(pause, RUBY_RE.sub(ruby, text or ""))


# 書式の外に残っていたら崩れとみなす記号。
#   ｜ | 《 》 … ナレーションで普段使わないので、残っていれば書式の書き損じ
#   ［間 [間  … 間の書式の書き損じ。［注］のような普通の括弧は対象にしない
_STRAY_RE = re.compile(r"[｜|《》]|[［\[]間")
# ｜ を書き忘れたルビ（漢字《よみ》）。青空文庫では直前の漢字に掛かるが、
# ここでは範囲を決められないので、1 件の警告にまとめて ｜ を促す
_ORPHAN_RUBY_RE = re.compile(r"《[^《》\n]+》")
_STRAY_MESSAGES = {
    "｜": "｜ の後に 《よみ》 がありません",
    "|": "| の後に 《よみ》 がありません",
    "《": "《 に対応する ｜ または 》 がありません（読みを付ける語の前に ｜ を置いてください）",
    "》": "》 に対応する 《 がありません",
}


@dataclass(frozen=True)
class MarkupProblem:
    line: int       # 1 始まり
    column: int     # 1 始まり
    message: str


def inspect_markup(text: str | None) -> list[MarkupProblem]:
    """崩れた書式と、上限を超えた間を、行と列つきで返す。"""
    text = text or ""
    problems: list[tuple[int, str]] = []

    # 正しい書式を同じ長さの空白で塗りつぶしてから、残った記号を探す。
    # 塗りつぶすことで、位置（行・列）が元の文字列とずれない。
    masked = list(text)
    for m in list(RUBY_RE.finditer(text)) + list(PAUSE_RE.finditer(text)):
        masked[m.start():m.end()] = " " * (m.end() - m.start())
        if m.re is PAUSE_RE and m.group(1) and float(m.group(1)) > MAX_PAUSE_SEC:
            problems.append((m.start(), f"間は最大 {_format_seconds(MAX_PAUSE_SEC)} 秒です"
                                        f"（{m.group(1)} 秒は {_format_seconds(MAX_PAUSE_SEC)} 秒になります）"))
    for m in _ORPHAN_RUBY_RE.finditer("".join(masked)):
        masked[m.start():m.end()] = " " * (m.end() - m.start())
        problems.append((m.start(), "《よみ》 の前に ｜ がありません（読みを付ける語の前に ｜ を置いてください）"))
    for m in _STRAY_RE.finditer("".join(masked)):
        token = m.group(0)
        message = _STRAY_MESSAGES.get(token, "間の書き方が正しくありません（［間］ または ［間:1.5］）")
        problems.append((m.start(), message))

    out = []
    for pos, message in sorted(problems):
        line = text.count("\n", 0, pos) + 1
        column = pos - (text.rfind("\n", 0, pos) + 1) + 1
        out.append(MarkupProblem(line, column, message))
    return out


# ==========================================================================
# 読みの推定（#73）
# ==========================================================================

_kakasi = None


def guess_reading(surface: str, lexicon: "Lexicon" = EMPTY_LEXICON) -> tuple[str, str]:
    """選んだ語の今の読み（推定）と、その出どころを返す。

    辞書・AI の読みにちょうど一致すれば、それを使う（出どころはその範囲）。
    そうでなければ、辞書を当てたうえで残りを pykakasi で仮名にする（出どころは "guess"）。
    pykakasi の読みは形態素の辞書による推定で、文脈による読み分けはできない。
    あくまで読みの指定画面の初期値で、人が直す前提。
    """
    surface = surface.strip()
    if surface in lexicon.entries:
        reading, source = lexicon.entries[surface]
        return reading, source
    text = build_reading(surface, lexicon).text
    global _kakasi
    try:
        if _kakasi is None:
            import pykakasi
            _kakasi = pykakasi.kakasi()
        text = "".join(part["hira"] for part in _kakasi.convert(text))
    except ImportError:
        pass    # pykakasi が無い環境では、辞書を当てただけの文字列を返す
    return text, "guess"
