import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from core.clock import utcnow


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # リレーション
    videos: Mapped[list["Video"]] = relationship("Video", back_populates="project", cascade="all, delete-orphan")
    # プロジェクトの読み辞書（#60）。プロジェクトを消したら一緒に消す。
    # SQLite は外部キーの ON DELETE を既定で効かせないため、ORM 側でも持たせる。
    reading_entries: Mapped[list["ReadingDictionaryEntry"]] = relationship(
        "ReadingDictionaryEntry", cascade="all, delete-orphan")
