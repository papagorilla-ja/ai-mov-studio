from pydantic import BaseModel, ConfigDict

from core.clock import UtcDatetime

class AudioWarning(BaseModel):
    """音声が崩れている可能性のあるシーン（#57）。"""
    scene_id: str
    scene_index: int
    title: str
    message: str


class GenerationHistoryRead(BaseModel):
    id: str
    video_id: str
    output_path: str | None = None
    status: str
    log_text: str | None = None
    error_message: str | None = None
    duration_sec: float | None = None
    file_size_bytes: int | None = None
    thumbnail_path: str | None = None
    started_at: UtcDatetime | None = None
    completed_at: UtcDatetime | None = None
    # 作り直しても直らなかった音声のあるシーン。空なら問題なし
    audio_warnings: list[AudioWarning] = []

    model_config = ConfigDict(from_attributes=True)

class GenerationStatus(BaseModel):
    """WebSocket で画面へ送る、動画生成の進捗（#96）。

    終わったかどうかは status で見る。終わったときの step は status と同じ値になる。
    （#100 で画面が status で判定するようになるまでは、以前の画面との互換のため
      完了を "rendering"、中止を "failed" として送っていた。#111 で片付けた）
    """
    generation_id: str
    # running / completed / failed / cancelled
    status: str
    # 実行中: queued / tts / composition / rendering / finishing
    # 終わり: completed / failed / cancelled
    step: str
    progress: float                     # 0.0〜1.0
    message: str | None = None
    error: str | None = None
    elapsed_sec: int = 0                # 生成を始めてからの秒数
    stage_eta_sec: int | None = None    # この段階の残りの目安（出せるときだけ）
