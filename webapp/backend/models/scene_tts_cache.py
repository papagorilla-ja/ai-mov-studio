"""シーン TTS キャッシュ — ナレーション音声の再利用判定に使用する"""
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base


class SceneTtsCache(Base):
    __tablename__ = "scene_tts_cache"

    # シーン ID を PK とする（1 シーン = 1 キャッシュエントリ）
    scene_id: Mapped[str] = mapped_column(String, ForeignKey("scenes.id", ondelete="CASCADE"), primary_key=True)
    # ハッシュ入力: 読み上げ用テキスト + 話者 + 参照音声のパス（+ 台詞・区切り）の MD5
    narration_hash: Mapped[str] = mapped_column(String, nullable=False)
    # 生成済み WAV ファイルの絶対パス
    audio_path: Mapped[str] = mapped_column(Text, nullable=False)
    # 参照音声ファイルの「更新時刻とサイズ」（#98）。録り直すと変わるので、
    # 違っていれば合成し直す。NULL は記録する前のキャッシュ（そのまま使ってから記録する）
    ref_signature: Mapped[str | None] = mapped_column(Text)
