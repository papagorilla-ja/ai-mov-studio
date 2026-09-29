"""1 シーンぶんの音声合成。動画の生成と試聴で同じものを使う（#98）。

以前は試聴と本番で合成の条件が違った（シードはシーンの ID と動画の ID、
区切りは試聴だけ使わない）。そのため試聴で良かった声と動画の声が同じにならず、
試聴で合成した音声も捨てていた（音声合成は動画生成の時間の 5〜6 割を占める）。

ここに次をまとめ、両方から呼ぶ。
  - prepare         … 何を・誰の声で・どう読むか（読み上げ用テキスト・台詞・区切り・話者）
  - cache_usable    … 前に合成した音声（キャッシュ）がそのまま使えるか
  - synthesize      … 合成する
  - apply_stats     … 合成で分かったこと（区切りの秒数・崩れの区間）をシーンに残す
  - remember        … キャッシュに記録する
"""
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from models.scene import Scene
from models.scene_tts_cache import SceneTtsCache
from models.speaker import Speaker
from services.reading import Lexicon, build_reading
from services.tts_service import compute_tts_hash, synthesize_scene_audio

# 話者が決まっていないシーンを読む声（seed_data のシステム話者と同じ参照音声）
DEFAULT_REFERENCE_PATH = "/app/voice_samples/default/reference.wav"


# ─── ナレーションの区切り（#3） ────────────────────────────

def narration_segments(scene) -> list[str] | None:
    """シーンに保存されたナレーションの区切りを取り出す。

    **本文と一致するときだけ**返す。区切りがあると音声合成は本文ではなく
    区切りの文字列を読むため、食い違ったまま使うと古い文章が読み上げられる。

    以前は「内容生成の時点で本文と一致させているから形だけ見ればよい」と
    していたが、生成後に本文が変わる経路（手で編集して保存・AI ナレーション
    生成など）では区切りが古いまま残っていた（#48）。書き込み側でも消して
    いるが、経路が増えても漏れないよう、使う直前にここで照合する。

    空白の違いは無視する。改行や空白を足しただけで同期（#3）を失わないため。
    食い違っても音声合成は止めない（区切りが無いものとして本文を読む）。
    """
    raw = getattr(scene, "narration_segments_json", None)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    texts = data.get("texts") if isinstance(data, dict) else None
    if not isinstance(texts, list) or len(texts) < 2:
        return None
    squeeze = lambda t: "".join(str(t or "").split())
    if squeeze("".join(texts)) != squeeze(getattr(scene, "narration_text", "")):
        return None
    return texts


def store_segment_starts(scene, starts) -> None:
    """区切りが始まる秒数をシーンに書き戻す。

    秒数が取れなかった場合（破綻して分割再合成が走ったなど）は空配列を入れる。
    古い秒数を残すと語られていない項目が先に出てしまうので消すのだが、
    キーごと消すと「まだ測っていない」と区別が付かなくなり、
    segment_starts_missing が毎回キャッシュを捨てて合成し直してしまう。
    「測ったが取れなかった」印として空配列を残す。
    """
    raw = getattr(scene, "narration_segments_json", None)
    if not raw:
        return
    try:
        data = json.loads(raw)
    except Exception:
        return
    if not isinstance(data, dict):
        return
    data["starts"] = [round(float(x), 3) for x in starts] if starts else []
    scene.narration_segments_json = json.dumps(data, ensure_ascii=False)


def segment_starts_missing(scene) -> bool:
    """区切りはあるのに、その秒数をまだ一度も測っていないか。

    秒数は音声合成のときにしか採れない。キャッシュが効くと合成を飛ばすため、
    区切りだけあって秒数が無いシーンは放っておくと永久に埋まらない。
    実際、区切りを導入した直後の生成では、TTS サーバーのプロセスが
    X-Chunk-Starts を返さない古いままだったために全シーンの秒数が空になり、
    そのあと何度生成し直しても均等配分のままだった。
    そういうシーンはキャッシュを使わず合成し直して秒数を採る。
    """
    if narration_segments(scene) is None:
        return False
    try:
        data = json.loads(getattr(scene, "narration_segments_json", None) or "")
    except Exception:
        return False
    # キーがあれば測定済み（空配列は「測ったが取れなかった」）。
    return isinstance(data, dict) and "starts" not in data


# ─── 話者 ───────────────────────────────────────────────

class SpeakerLookup:
    """話者を ID で引く。同じ話者を何度も DB に問い合わせない（生成では全シーンぶん引く）。"""

    def __init__(self, db: AsyncSession):
        self._db = db
        self._cache: dict[str, Speaker | None] = {}

    async def get(self, speaker_id: str | None) -> Speaker | None:
        if not speaker_id:
            return None
        if speaker_id not in self._cache:
            self._cache[speaker_id] = await self._db.get(Speaker, speaker_id)
        return self._cache[speaker_id]


def reference_signature(*speakers: Speaker | None) -> str:
    """参照音声ファイルの「更新時刻とサイズ」。録り直すと変わる。

    参照音声は録り直しても同じパスに上書きされるため、パスだけを見る
    キャッシュの判定では気づけず、古い声のまま生成されていた。
    """
    parts = []
    for speaker in speakers:
        path = (speaker.reference_audio_path if speaker else None) or DEFAULT_REFERENCE_PATH
        try:
            st = Path(path).stat()
            parts.append(f"{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append("missing")
    return "|".join(parts)


# ─── 準備 ───────────────────────────────────────────────

@dataclass
class SceneTtsInput:
    """1 シーンぶんの音声合成に渡すもの。"""
    text: str                       # 読み上げ用テキスト（ルビ・辞書・AI の読みを当てたもの）
    dialog_lines: list[dict]        # 対話レイアウトの台詞（それ以外は空）
    segments: list[str] | None      # ナレーションの区切り（読み上げ用テキストに直したもの）
    speaker_a: Speaker | None
    speaker_b: Speaker | None
    narration_hash: str             # キャッシュの判定に使うハッシュ
    ref_signature: str              # 参照音声ファイルの更新時刻とサイズ


async def prepare(scene: Scene, style, lexicon: Lexicon, speakers: SpeakerLookup) -> SceneTtsInput:
    """シーンを何と誰の声で読むかを決める。

    読み上げ用テキストはルビ・辞書・AI の読みで書き換えたもの（#60）。本文は変えない。
    キャッシュの判定もこの文字列で行うので、辞書を直すとそのシーンだけ作り直される。
    """
    text = build_reading(scene.narration_text or " ", lexicon).text

    speaker_a_id = scene.speaker_id or getattr(style, "default_speaker_id", None)
    speaker_a = await speakers.get(speaker_a_id)

    dialog_lines: list[dict] = []
    if scene.layout_type == "chat_dialog" and scene.slide_content_json:
        try:
            dialog_lines = json.loads(scene.slide_content_json).get("lines", [])
        except Exception:
            dialog_lines = []
    # 台詞にもルビと辞書を当てる
    dialog_content = scene.slide_content_json
    if dialog_lines:
        read_lines = [{**line, "text": build_reading(line.get("text", ""), lexicon).text}
                      for line in dialog_lines if isinstance(line, dict)]
        if read_lines != dialog_lines:
            # 書き換えたときだけキャッシュの判定に反映する。書き換えが無ければ
            # 従来と同じ値のままにして、既存のキャッシュを無駄に捨てない。
            dialog_content = json.dumps(read_lines, ensure_ascii=False)
        dialog_lines = read_lines

    segments = narration_segments(scene)
    if segments:
        segments = [build_reading(seg, lexicon).text for seg in segments]

    # 話者 B は対話レイアウトだけ
    speaker_b_id = None
    speaker_b = None
    if dialog_lines:
        speaker_b_id = scene.speaker_b_id or getattr(style, "default_speaker_b_id", None)
        speaker_b = await speakers.get(speaker_b_id)

    narration_hash = compute_tts_hash(
        text=text,
        speaker_a_id=speaker_a_id,
        ref_path_a=speaker_a.reference_audio_path if speaker_a else None,
        dialog_lines=dialog_lines,
        speaker_b_id=speaker_b_id,
        ref_path_b=speaker_b.reference_audio_path if speaker_b else None,
        slide_content_json=dialog_content,
        narration_segments=segments,
    )
    signature = reference_signature(speaker_a, speaker_b) if dialog_lines else reference_signature(speaker_a)
    return SceneTtsInput(text, dialog_lines, segments, speaker_a, speaker_b, narration_hash, signature)


# ─── キャッシュ ──────────────────────────────────────────

def cache_usable(cached: SceneTtsCache | None, inp: SceneTtsInput, scene: Scene,
                 untrusted_paths: set[str] = frozenset()) -> bool:
    """前に合成した音声がそのまま使えるか。

    参照音声の記録（ref_signature）が無い既存のキャッシュは使ってよい。
    一斉に合成し直させないため。使ったときに記録を付ける（remember）。
    """
    return (
        cached is not None
        and cached.narration_hash == inp.narration_hash
        and cached.audio_path not in untrusted_paths
        and (cached.ref_signature is None or cached.ref_signature == inp.ref_signature)
        and Path(cached.audio_path).exists()
        and not segment_starts_missing(scene)
    )


def remember(db: AsyncSession, cached: SceneTtsCache | None, scene_id: str,
             inp: SceneTtsInput, raw_path: Path) -> SceneTtsCache:
    """キャッシュに記録する（無ければ作る）。"""
    if cached is None:
        cached = SceneTtsCache(scene_id=scene_id)
        db.add(cached)
    cached.narration_hash = inp.narration_hash
    cached.audio_path = str(raw_path)
    cached.ref_signature = inp.ref_signature
    return cached


# ─── 合成 ───────────────────────────────────────────────

async def synthesize(inp: SceneTtsInput, raw_path: Path, seed: int) -> dict:
    """合成して raw_path（等倍）に書き、診断情報を返す。シーンには書き込まない。"""
    stats: dict = {}
    await synthesize_scene_audio(
        text=inp.text,
        dialog_lines=inp.dialog_lines,
        speaker_a=inp.speaker_a,
        speaker_b=inp.speaker_b,
        output_wav_path=raw_path,
        seed=seed,
        stats=stats,
        segments=inp.segments,
    )
    return stats


def apply_stats(scene: Scene, stats: dict) -> None:
    """合成で分かったことをシーンに残す。キャッシュを使う次回以降も同じ音声なので使い回す。

      - 区切りが始まる秒数（要素を出す時刻に使う）
      - 作り直しても直らなかった区間（#57。画面で知らせる）
    """
    store_segment_starts(scene, stats.get("segment_starts"))
    scene.narration_audio_degraded = stats.get("degraded_ranges") or None
