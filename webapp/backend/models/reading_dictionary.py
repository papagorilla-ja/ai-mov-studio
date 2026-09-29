"""読み辞書（#60）。TTS に渡す前に、表記を読みへ置き換えるための対応表。

範囲は 3 つ（#73 でシーンを追加）。
  全体         project_id も scene_id も NULL
  プロジェクト  project_id に値がある
  シーン       scene_id に値がある（project_id は NULL）。本文に記号を入れずに
               「このシーンだけ」読みを変えるためのもの
同じ表記が複数の範囲にあれば、狭い範囲を優先する（シーン → プロジェクト → 全体、services.reading）。

表記の重複は同じ辞書の中では許さない。SQLite の UNIQUE は NULL 同士を
別物とみなすため全体辞書では効かない。重複の検査はルーター側で行う。
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from core.clock import utcnow


class ReadingDictionaryEntry(Base):
    __tablename__ = "reading_dictionary"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # NULL は全体辞書（scene_id も NULL のとき）
    project_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    # シーンだけの読み。値があるときは project_id を NULL にする
    scene_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    surface: Mapped[str] = mapped_column(String, nullable=False)   # 表記（例: 賢者の石）
    reading: Mapped[str] = mapped_column(String, nullable=False)   # 読み（例: けんじゃのいし）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False)
