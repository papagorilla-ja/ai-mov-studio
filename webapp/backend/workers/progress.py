"""動画生成の進捗の知らせ方（#96）。

画面へは WebSocket で schemas.generation.GenerationStatus の形の dict を送る。
全体の進捗（0〜1）の中で、各段階が占める範囲はここで決める。

以前は レンダリングを始めた時点で 80% にしたまま、終わるまで何も送っていなかった。
実際の生成では、レンダリングが全体の 3〜4 割の時間を占めるため、
その間ずっと進捗が止まって見えていた。
"""
import re
import time
from collections.abc import Awaitable, Callable

from schemas.generation import GenerationStatus

# 全体の進捗のうち、各段階が占める範囲。実際の生成履歴では、音声を合成し直す
# 動画で音声合成が約 6 割、レンダリングが約 4 割の時間だった。
TTS_RANGE = (0.02, 0.55)
COMPOSITION_AT = 0.57
RENDER_RANGE = (0.58, 0.96)
FINISHING_AT = 0.97

# 残りの目安を出し始める進み具合。進み始めは速さが安定せず、当てにならない
ETA_MIN_FRACTION = 0.05

# hyperframes が出す段階（英語）を、画面の文言にする。前方一致で引く
_RENDER_STAGE_LABELS = (
    ("Capturing frame", "フレームを撮影中"),
    ("Encoding", "動画をエンコード中"),
    ("Assembling", "動画を組み立て中"),
    ("Processing audio", "音声を処理中"),
    ("Render complete", "書き出し完了"),
)
_FRAME_COUNT_RE = re.compile(r"(\d+)/(\d+)")


def render_stage_label(stage: str) -> str:
    """hyperframes の段階を日本語にする。撮影中はフレーム数も添える。"""
    for prefix, label in _RENDER_STAGE_LABELS:
        if stage.startswith(prefix):
            m = _FRAME_COUNT_RE.search(stage) if prefix == "Capturing frame" else None
            return f"{label} {m.group(1)}/{m.group(2)}" if m else label
    return "準備中"


def span(value_range: tuple[float, float], fraction: float) -> float:
    """範囲 (始め, 終わり) の中で、進み具合 fraction（0〜1）に当たる位置。"""
    start, end = value_range
    return start + (end - start) * min(max(fraction, 0.0), 1.0)


def remaining_seconds(elapsed: float, fraction: float) -> int | None:
    """かかった時間と進み具合から、残りの目安（秒）。出せなければ None。"""
    if not (ETA_MIN_FRACTION <= fraction < 1.0):
        return None
    return int(elapsed * (1.0 - fraction) / fraction)


class GenerationProgress:
    """1 回の生成の進捗を、画面へ送る形に整えて送る。"""

    def __init__(self, generation_id: str, send: Callable[[dict], Awaitable[None]]):
        self.generation_id = generation_id
        self._send = send
        self._started = time.monotonic()

    def _message(self, status: str, step: str, progress: float, message: str | None,
                 error: str | None = None, stage_eta_sec: int | None = None) -> dict:
        return GenerationStatus(
            generation_id=self.generation_id,
            status=status,
            step=step,
            progress=round(progress, 4),
            message=message,
            error=error,
            elapsed_sec=int(time.monotonic() - self._started),
            stage_eta_sec=stage_eta_sec,
        ).model_dump()

    def queued(self) -> dict:
        """生成を受け付けた直後の進捗（まだ送らない。接続したときの最初の 1 件になる）。"""
        return self._message("running", "queued", 0.0, "生成の準備をしています...")

    async def report(self, step: str, progress: float, message: str,
                     *, stage_eta_sec: int | None = None) -> None:
        await self._send(self._message("running", step, progress, message,
                                       stage_eta_sec=stage_eta_sec))

    async def completed(self, message: str) -> None:
        await self._send(self._message("completed", "completed", 1.0, message))

    async def failed(self, error: str) -> None:
        await self._send(self._message("failed", "failed", 1.0, f"エラー: {error}", error=error))

    async def cancelled(self) -> None:
        # 中止は失敗ではないので error は付けない（#111）
        await self._send(self._message("cancelled", "cancelled", 1.0, "生成を中止しました"))
