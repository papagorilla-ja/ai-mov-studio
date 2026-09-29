import json
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from core.clock import utcnow


class GenerationHistory(Base):
    __tablename__ = "generation_history"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id: Mapped[str] = mapped_column(String, ForeignKey("videos.id"), nullable=False)
    output_path: Mapped[str | None] = mapped_column(Text)
    # running / completed / failed
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    log_text: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    duration_sec: Mapped[float | None] = mapped_column(Float)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    thumbnail_path: Mapped[str | None] = mapped_column(Text)
    # 音声が崩れている可能性のあるシーンの一覧（#57）。JSON の配列で
    # [{scene_id, scene_index, title, message}]。無ければ NULL
    audio_warnings_json: Mapped[str | None] = mapped_column(Text)

    @property
    def audio_warnings(self) -> list[dict]:
        """audio_warnings_json を一覧にして返す（API の応答用）。"""
        try:
            data = json.loads(self.audio_warnings_json or "[]")
        except ValueError:
            return []
        return data if isinstance(data, list) else []

    # リレーション
    video: Mapped["Video"] = relationship("Video", back_populates="generation_history")
