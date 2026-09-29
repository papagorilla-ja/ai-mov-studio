import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from core.clock import utcnow


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(String, ForeignKey("scenarios.id"), nullable=False)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String)
    # text_only / text_left_image_right / full_image / comparison / bullet_list / chat_dialog / section_header
    layout_type: Mapped[str] = mapped_column(String, nullable=False, default="text_only")
    # JSON: スライド表示テキスト等 {title, body, bullet_points, ...}
    slide_content_json: Mapped[str | None] = mapped_column(Text)
    narration_text: Mapped[str | None] = mapped_column(Text)
    # チャットのアウトライン段階で決めた「このシーンで扱う内容のあらすじ」。
    # ナレーション本文・スライド内容の深堀り時の起点（意図）として使う。
    outline_summary: Mapped[str | None] = mapped_column(Text)
    narration_audio_path: Mapped[str | None] = mapped_column(Text)
    narration_audio_duration: Mapped[float | None] = mapped_column(Float)
    # ナレーションを項目に対応させて分けたもの。
    #   {"texts": ["導入", "項目1について", …], "starts": [0.0, 4.2, …]}
    # texts は内容生成のときに、starts は音声合成のときに入る。
    # 1 番目が導入、2 番目以降が項目 1, 2, 3 … に対応する。
    # starts があると、要素を「その項目を語り始めた秒数」に合わせて出せる。
    # 無ければ従来どおりシーン尺への均等配分になる。
    narration_segments_json: Mapped[str | None] = mapped_column(Text)
    # TTS が作り直しても直せなかった区間（#57）。等倍の音声での秒数を
    # 「開始-終了;開始-終了」の形で持つ（TTS サーバーの X-Degraded-Ranges そのまま）。
    # 話速は後から変えられるので、秒数は等倍のまま持ち、文言にするときに割る。
    narration_audio_degraded: Mapped[str | None] = mapped_column(Text)
    # 上を画面向けの文言にしたもの。音声を確定させるたびに作り直す。NULL は問題なし
    narration_audio_warning: Mapped[str | None] = mapped_column(Text)
    # AI が選んだ読み（#60）。{"hash": ナレーションの MD5, "readings": [{surface, reading}]}
    # 書き換えた全文ではなく対応表で持つ。辞書を後から直したときに、
    # AI を動かし直さなくても反映されるようにするため。
    # hash が今のナレーションと違えば古い（作り直しの対象）。
    narration_ai_readings_json: Mapped[str | None] = mapped_column(Text)
    # このシーンだけの読み（#73）。シーンを消したら一緒に消す
    reading_entries: Mapped[list["ReadingDictionaryEntry"]] = relationship(
        "ReadingDictionaryEntry", cascade="all, delete-orphan")
    speaker_id: Mapped[str | None] = mapped_column(String, ForeignKey("speakers.id"))
    speaker_b_id: Mapped[str | None] = mapped_column(String, ForeignKey("speakers.id"))
    # ナレーションの長さの上書き。NULL は「動画の既定に従う」。
    narration_length: Mapped[str | None] = mapped_column(String)
    # ユーザーが見せ方を明示的に選んだか。
    # False（おまかせ）なら内容生成のたびに AI が選び直し、
    # True なら layout_type を動かさない。シナリオ作成で AI が選んだ段階は False。
    layout_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False,
                                                server_default="0")
    # タイムライン計算後に保存
    data_start: Mapped[float | None] = mapped_column(Float)
    data_duration: Mapped[float | None] = mapped_column(Float)
    # AI調整または手動編集によるシーン単位のHTML/CSS上書き（NULL=自動生成のまま）
    custom_html: Mapped[str | None] = mapped_column(Text)
    custom_css: Mapped[str | None] = mapped_column(Text)
    # 外部の画像生成AI（Gemini 等）に貼り付けるためのプロンプト
    image_prompt: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # リレーション
    scenario: Mapped["Scenario"] = relationship("Scenario", back_populates="scenes")
    assets: Mapped[list["SceneAsset"]] = relationship("SceneAsset", back_populates="scene", cascade="all, delete-orphan")
    speaker: Mapped["Speaker | None"] = relationship("Speaker", foreign_keys=[speaker_id])
    speaker_b: Mapped["Speaker | None"] = relationship("Speaker", foreign_keys=[speaker_b_id])
