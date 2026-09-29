"""シーンのナレーションを Qwen3-TTS で音声化するサービス。

■ 処理の流れ（これだけ）
  1. ナレーション本文を TTS が安全に扱えるチャンクに分割する (split_with_pauses)
  2. 1シーン分のチャンクをまとめて TTS サーバーに 1 リクエストで投げる
  3. 返ってきた WAV（連結・正規化済み）をそのまま保存する

Qwen3-TTS は長文を1回で投げると EOS を出せずに雑音を生成し続けて破綻するため、
チャンク分割は必須である（詳細は docs/antigravity_fix14_tts_overhaul.md）。
チャンクの連結・無音トリム・音量正規化は TTS サーバー側が行うので、
ここでは ffmpeg も一時ファイルも使わない。
"""
import hashlib
import json
import math
import re
import unicodedata
import wave
from pathlib import Path

import httpx

from core.config import settings
from services.reading import PAUSE_RE, pause_seconds

# キャッシュ判定ハッシュのバージョン。TTS の生成方式を変えたら必ず上げること。
# （上げないと、破綻した過去の WAV が SceneTtsCache 経由で再利用されてしまう）
TTS_PIPELINE_VERSION = "fix14"

# TTS 1 チャンクあたりの最大文字数。
#
# この値は「破綻しにくさ」ではなく **生成中のメモリのピーク** で決めている。
# MPS のピークはチャンクの長さだけで決まり、バッチ数や 1 リクエストあたりの
# チャンク数には影響されない（実測）。
#
#   チャンク長   ピーク        1 文字あたりの生成速度
#   120 字       30.8GB 超     6.1 字/秒
#    60 字       23.6GB        15.8 字/秒
#    45 字       18.4GB        —
#
# 120 字では破綻していなくても 30GB を超えており、そこへ破綻（EOS 未発火で
# 上限まで生成し切る）が重なると 71GB に達し、macOS にプロセスを
# 強制終了された。短いチャンクはメモリが少なく、しかも速い。
#
# 以前は「128〜142 文字帯は破綻ゼロ」という実測を根拠に 120 としていたが、
# 実際には 94 字・110 字でも破綻が起きており、その前提は成り立っていない。
DEFAULT_MAX_CHUNK_CHARS = 60
# これ未満の断片は前後のチャンクに吸収する
MIN_CHUNK_CHARS = 8

# 生成中のメモリのピークがこれを超えたら生成ログで警告する。
# 64GB のマシンで他のアプリが 20〜25GB 使っている前提での目安。
# これを常に超えるようなら tts_max_chunk_chars をさらに下げる。
TTS_PEAK_WARN_MB = 28_000

# ヘルスチェックのタイムアウト（秒）。合成本体とは別に短く取る。
TTS_HEALTH_TIMEOUT_SEC = 5


def _max_chunk_chars() -> int:
    return int(getattr(settings, "tts_max_chunk_chars", DEFAULT_MAX_CHUNK_CHARS))


def derive_seed(key: str) -> int:
    """キー文字列から決定的なシードを導出する。

    シードを固定することで、同じ原稿からは常に同じ音声が得られる。
    （デバッグの再現性、キャッシュとの整合性、声質のブレ防止のため）
    """
    return int(hashlib.md5(key.encode("utf-8")).hexdigest()[:8], 16)


def compute_tts_hash(
    text: str,
    speaker_a_id: str | None,
    ref_path_a: str | None,
    dialog_lines: list[dict] | None = None,
    speaker_b_id: str | None = None,
    ref_path_b: str | None = None,
    slide_content_json: dict | str | None = None,
    narration_segments: list[str] | None = None
) -> str:
    """TTS用のキャッシュ判定ハッシュを算出する"""
    if dialog_lines:
        content_str = ""
        if slide_content_json:
            if isinstance(slide_content_json, dict):
                content_str = json.dumps(slide_content_json, ensure_ascii=False)
            else:
                content_str = str(slide_content_json)
        hash_raw = (
            f"{TTS_PIPELINE_VERSION}|{content_str}"
            f"|{speaker_a_id or ''}|{ref_path_a or ''}"
            f"|{speaker_b_id or ''}|{ref_path_b or ''}"
        )
    else:
        hash_raw = f"{TTS_PIPELINE_VERSION}|{text or ''}|{speaker_a_id or ''}|{ref_path_a or ''}"
    # 区切りはチャンクの切れ目を変える（split_segments_for_tts は区切りを
    # またがない）。切れ目が変われば間の取り方も変わり、音声そのものが変わる。
    # 本文が同じでも区切りだけ変わったときにキャッシュを使い回さないよう、
    # ここに含める。区切りが無いときは従来と同じ値のままにして、
    # 既存のキャッシュを無駄に捨てない。
    if narration_segments:
        hash_raw += "|seg:" + "\x1f".join(narration_segments)
    return hashlib.md5(hash_raw.encode("utf-8")).hexdigest()


# ─── テキストの正規化とチャンク分割 ───────────────────────
def normalize_for_tts(text: str) -> str:
    """TTS に渡す前の軽量な正規化。読み上げに不要な表記ゆれを潰す。"""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    # 行頭の markdown 記号 (- * # >) を除去
    t = re.sub(r"^[ \t]*[-*#>]+[ \t]*", "", t, flags=re.MULTILINE)
    # 強調記号は読み上げ対象外
    t = t.replace("**", "").replace("__", "")
    # 空白の圧縮
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{2,}", "\n", t)
    # 句読点で終わっていない改行は文の区切りとみなす。
    # （これがないと、行が連結されたときに「見出し本文です」のように読まれてしまう）
    t = re.sub(r"(?<=[^\s。．！？!?、，,])\n", "。\n", t)
    return t.strip()


# (チャンクの文字列, その後に入れる間の秒数)。間が None なら TTS サーバーが
# 句読点に応じて決める（gap_after）。
Chunk = tuple[str, float | None]


def split_with_pauses(text: str, max_chars: int | None = None) -> list[Chunk]:
    """間の指定（［間］・［間:秒］、#60）で切ってから、各部分をチャンクに分割する。

    間の直前のチャンクに、その秒数を持たせる。続けて書かれた間は足し合わせる。
    先頭の間（前にチャンクが無い）は、置く場所が無いので捨てる。
    """
    chunks: list[Chunk] = []
    cursor = 0
    for m in PAUSE_RE.finditer(text or ""):
        chunks.extend((c, None) for c in _split_plain(text[cursor:m.start()], max_chars))
        if chunks:
            prev_text, prev_pause = chunks[-1]
            chunks[-1] = (prev_text, (prev_pause or 0.0) + pause_seconds(m))
        cursor = m.end()
    chunks.extend((c, None) for c in _split_plain((text or "")[cursor:], max_chars))
    return chunks


def _split_plain(text: str, max_chars: int | None = None) -> list[str]:
    """テキストを TTS が安全に処理できるチャンク列に分割する（間の指定を含まないこと）。

    1) 句点・改行で文に分割
    2) max_chars を超える文は読点でさらに分割
    3) それでも超える場合は max_chars で強制分割
    4) 隣接する断片を max_chars 以内でマージ（呼び出し回数を減らす）
    """
    limit = max_chars or _max_chunk_chars()
    text = normalize_for_tts(text)
    if not text:
        return []

    # 1) 文分割
    sentences = [s.strip() for s in re.split(r"(?<=[。．！？!?\n])", text) if s.strip()]

    # 2)-3) 長すぎる文をさらに割る
    pieces: list[str] = []
    for s in sentences:
        if len(s) <= limit:
            pieces.append(s)
            continue
        for sub in [x.strip() for x in re.split(r"(?<=[、，,])", s) if x.strip()]:
            while len(sub) > limit:
                pieces.append(sub[:limit])
                sub = sub[limit:]
            if sub:
                pieces.append(sub)

    # 4) マージ
    chunks: list[str] = []
    for p in pieces:
        if chunks and len(chunks[-1]) + len(p) <= limit:
            chunks[-1] += p
        elif chunks and len(p) < MIN_CHUNK_CHARS:
            chunks[-1] += p          # 極小断片は長さ超過を許容して吸収
        else:
            chunks.append(p)

    return chunks


def split_segments_for_tts(segments: list[str], max_chars: int | None = None) -> tuple[list[Chunk], list[int]]:
    """区切りごとに分割し、(チャンク列, 各区切りが始まるチャンク番号) を返す。

    区切りをまたいでチャンクを作らないのが肝。またいでしまうと
    「この区切りが何秒から始まるか」が測れなくなり、要素を出す時刻が決められない。

    空の区切り（導入が不要なときなど）は、直後の区切りと同じ開始位置を指す。
    """
    chunks: list[Chunk] = []
    starts: list[int] = []
    for seg in segments:
        starts.append(len(chunks))
        if seg and seg.strip():
            chunks.extend(split_with_pauses(seg, max_chars))
    return chunks, starts


def segment_start_seconds(seg_chunk_index: list[int], chunk_starts: list[float],
                          total_sec: float) -> list[float]:
    """区切りが始まる秒数を求める。

    chunk_starts は TTS サーバーが返した「各チャンクが始まる秒数」。
    チャンク数が合わない（破綻して分割再合成が走ったなど）場合は、
    無理に対応づけず空を返す。ずれた秒数で要素を出すくらいなら、
    従来どおりの均等配分に落とす方が安全。
    """
    if not seg_chunk_index or not chunk_starts:
        return []
    if max(seg_chunk_index) >= len(chunk_starts):
        print(f"[tts] チャンク数が合わないため区切りの秒数は使いません "
              f"(必要 {max(seg_chunk_index)+1} / 実際 {len(chunk_starts)})")
        return []
    out = [chunk_starts[i] for i in seg_chunk_index]
    # 単調増加で、尺の内側に収まっていること
    if any(b < a for a, b in zip(out, out[1:])) or out[-1] > total_sec:
        return []
    return out


def generate_silent_wav(output_wav_path: Path, duration_sec: float = 2.0) -> bytes:
    """24kHz, 16-bit, モノラルの無音 WAV ファイルを指定秒数生成して保存し、バイト列を返す。"""
    sample_rate = 24000
    num_frames = int(sample_rate * duration_sec)
    silence_frames = b"\x00\x00" * num_frames

    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(silence_frames)

    return output_wav_path.read_bytes()


def _build_items(text: str, dialog_lines: list[dict] | None, speaker_a, speaker_b,
                 segments: list[str] | None = None) -> tuple[list[dict], list[int]]:
    """TTS サーバーに渡すチャンク列と、各区切りが始まるチャンク番号を返す。

    segments を渡すと区切りをまたがないように分割する。またぐと
    「その区切りが何秒から始まるか」が測れなくなる。
    """

    def make(chunk: Chunk, speaker) -> dict:
        chunk_text, pause = chunk
        item = {
            "text": chunk_text,
            "language": speaker.language if speaker and speaker.language else "ja",
        }
        if speaker and speaker.reference_audio_path:
            item["reference_audio_path"] = speaker.reference_audio_path
        if pause is not None:
            # 間の指定（#60）。無ければ TTS サーバーが句読点から決める
            item["pause_after_sec"] = round(pause, 3)
        return item

    items: list[dict] = []
    seg_index: list[int] = []
    if dialog_lines:
        # 対話は話者が交互に変わるため、区切りの仕組みは使わない
        for line in dialog_lines:
            speaker = speaker_b if line.get("speaker") == "B" else speaker_a
            for chunk in split_with_pauses(line.get("text", "")):
                items.append(make(chunk, speaker))
    elif segments:
        chunks, seg_index = split_segments_for_tts(segments)
        for chunk in chunks:
            items.append(make(chunk, speaker_a))
    else:
        for chunk in split_with_pauses(text):
            items.append(make(chunk, speaker_a))
    return items, seg_index


async def ensure_tts_ready() -> None:
    """TTS サーバーが合成可能な状態かを確認し、駄目なら理由を明示して例外を送出する。

    既存音声の削除など、失敗すると後戻りできない処理の前に必ず呼ぶこと。
    確認せずに削除すると、TTS が停止していた場合に音声を失ったうえで合成にも失敗し、
    何も残らない状態になる。
    """
    url = f"{settings.qwen3_tts_base_url}/health"
    try:
        async with httpx.AsyncClient(timeout=TTS_HEALTH_TIMEOUT_SEC) as client:
            resp = await client.get(url)
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        raise RuntimeError(
            f"TTSサーバーに接続できません（起動していない可能性があります）: {url}"
            " — サーバーの起動を確認してから再実行してください。"
        ) from e
    except httpx.HTTPError as e:
        raise RuntimeError(
            f"TTSサーバーの状態を確認できません: {str(e) or repr(e)}"
        ) from e

    if resp.status_code != 200:
        raise RuntimeError(
            f"TTSサーバーが異常な応答を返しました (HTTP {resp.status_code})"
        )

    try:
        payload = resp.json()
    except ValueError as e:
        raise RuntimeError("TTSサーバーの応答を解釈できませんでした") from e

    # model_loaded が無い応答は Qwen3-TTS 以外のサーバー。
    # 設定ミス（例: レンダラーの URL を指定している）を「ロード中」と誤報しないよう分ける。
    if not isinstance(payload, dict) or "model_loaded" not in payload:
        raise RuntimeError(
            f"TTSサーバーではないサーバーが応答しました: {url}"
            " — 設定の TTS サーバー URL をご確認ください。"
        )

    if not payload["model_loaded"]:
        raise RuntimeError(
            "TTSサーバーはモデルのロード中です。しばらく待ってから再実行してください。"
        )


def parse_degraded_ranges(raw: str | None) -> list[tuple[float, float]]:
    """TTS サーバーの X-Degraded-Ranges（「開始-終了;…」）を読む。壊れた要素は捨てる。"""
    ranges = []
    for part in (raw or "").split(";"):
        try:
            a, b = (float(x) for x in part.split("-"))
        except ValueError:
            continue
        if b > a >= 0:
            ranges.append((a, b))
    return ranges


def audio_warning_message(raw_ranges: str | None, speed: float = 1.0) -> str | None:
    """直らなかった区間を、画面に出す文言にする。問題が無ければ None。

    秒数は等倍の音声での位置なので、読み上げ速度で割って実際の動画の位置に直す。
    範囲は広めに丸める（開始は切り捨て、終了は切り上げ）。狭く出すと、
    聞き直したときに崩れの手前や後ろを聞き逃す。
    """
    ranges = parse_degraded_ranges(raw_ranges)
    if not ranges:
        return None
    speed = speed if speed and speed > 0 else 1.0
    spans = "、".join(f"{int(a / speed)}〜{math.ceil(b / speed)} 秒" for a, b in ranges)
    return f"音声の {spans}が本文どおりに読まれていない可能性があります。音声を作り直してください。"


async def synthesize_scene_audio(
    text: str,
    dialog_lines: list[dict] | None,
    speaker_a,
    speaker_b,
    output_wav_path: Path,
    seed: int | None = None,
    stats: dict | None = None,
    segments: list[str] | None = None,
) -> bytes:
    """1シーン分の TTS 音声を合成し、output_wav_path に保存して WAV バイト列を返す。

    stats に dict を渡すと、チャンク数・リトライ回数・所要時間などの診断情報が格納される。
    """
    # テキストが空かつ対話行もない場合は TTS 呼び出しをスキップして無音を返す
    if not (text and text.strip()) and not dialog_lines:
        return generate_silent_wav(output_wav_path, duration_sec=2.0)

    items, seg_index = _build_items(text, dialog_lines, speaker_a, speaker_b, segments)
    if not items:
        return generate_silent_wav(output_wav_path, duration_sec=2.0)

    payload = {
        "items": items,
        "seed": seed,
        "gap_sec": getattr(settings, "tts_chunk_gap_sec", 0.28),
        "batch_size": getattr(settings, "tts_batch_size", 4),
    }

    timeout_val = getattr(settings, "tts_request_timeout", 1800)

    # 事前に TTS サーバーの状態を確認する。
    # 旧実装は接続エラーを握りつぶしていたが、httpx.ConnectError は HTTPError の
    # サブクラスであるため「サーバーが停止しているとき」にこそ機能していなかった。
    await ensure_tts_ready()

    async with httpx.AsyncClient(timeout=timeout_val) as client:
        try:
            resp = await client.post(f"{settings.qwen3_tts_base_url}/synthesize", json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 503:
                raise RuntimeError(
                    "TTSサーバーは起動中（モデルロード中）です。もうしばらくお待ちください。"
                ) from e
            raise RuntimeError(
                f"TTSサーバーエラー ({e.response.status_code}): {e.response.text}"
            ) from e
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise RuntimeError(
                f"TTSサーバー接続エラー（サーバーが起動していない可能性があります）: {str(e) or repr(e)}"
            ) from e
        except httpx.TimeoutException as e:
            raise RuntimeError(
                "TTS音声合成がタイムアウトしました。"
                "ナレーションが長い、またはCPU推論が遅い可能性があります。"
                "ナレーションを短くするか、TTSタイムアウト設定を延長してください。"
            ) from e
        except (httpx.RemoteProtocolError, httpx.ReadError) as e:
            # 応答を返さずに接続が切れた = TTS サーバーのプロセスが合成中に死んでいる。
            # 実例として、MPS のキャッシュ肥大で macOS に強制終了された事象があった。
            # 原文（"Server disconnected without sending a response."）だけでは
            # 原因も次の手も分からないため、確認先を明示する。
            raise RuntimeError(
                "TTSサーバーが応答を返さずに切断されました"
                "（合成中にサーバープロセスが停止した可能性があります）。"
                "メモリ不足による強制終了が主な原因です。"
                "data/tts_host.log を確認し、start.sh で再起動してから再実行してください。"
                f" 詳細: {str(e) or repr(e)}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"音声合成エラー: {str(e) or repr(e)}") from e

    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    output_wav_path.write_bytes(resp.content)

    if stats is not None:
        stats.update({
            "chunks": resp.headers.get("X-Chunk-Count"),
            "retries": resp.headers.get("X-Retry-Count"),
            "degraded": resp.headers.get("X-Degraded-Chunks"),
            "generate_sec": resp.headers.get("X-Generate-Seconds"),
            "audio_sec": resp.headers.get("X-Audio-Seconds"),
            "peak_mb": resp.headers.get("X-Peak-Memory-MB"),
            # 作り直しても直らなかった区間（等倍の秒数）。空文字なら問題なし
            "degraded_ranges": resp.headers.get("X-Degraded-Ranges") or "",
        })
        # 区切りが始まる秒数。要素の登場をナレーションに合わせるのに使う。
        if seg_index:
            raw = resp.headers.get("X-Chunk-Starts") or ""
            try:
                chunk_starts = [float(x) for x in raw.split(",") if x]
            except ValueError:
                chunk_starts = []
            total = float(resp.headers.get("X-Audio-Seconds") or 0)
            stats["segment_starts"] = segment_start_seconds(seg_index, chunk_starts, total)
    return resp.content
