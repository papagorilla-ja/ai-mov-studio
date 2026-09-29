"""読みの制御（#60）の入出力。"""
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.clock import UtcDatetime

# 表記に書式の記号が入っていると、ルビ・間の書式と区別できなくなる
_MARKUP_CHARS = re.compile(r"[｜|《》［］\[\]\n]")


def _clean(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError(f"{field}を入力してください")
    if _MARKUP_CHARS.search(value):
        raise ValueError(f"{field}に ｜《》［］ や改行は使えません")
    return value


class DictionaryEntryCreate(BaseModel):
    surface: str = Field(..., max_length=50, description="表記（例: 賢者の石）")
    reading: str = Field(..., max_length=100, description="読み（例: けんじゃのいし）")

    @field_validator("surface")
    @classmethod
    def _surface(cls, v): return _clean(v, "表記")

    @field_validator("reading")
    @classmethod
    def _reading(cls, v): return _clean(v, "読み")


class DictionaryEntryUpdate(BaseModel):
    surface: str | None = Field(default=None, max_length=50)
    reading: str | None = Field(default=None, max_length=100)

    @field_validator("surface")
    @classmethod
    def _surface(cls, v): return _clean(v, "表記")

    @field_validator("reading")
    @classmethod
    def _reading(cls, v): return _clean(v, "読み")


class DictionaryEntryRead(BaseModel):
    id: str
    project_id: str | None = None      # 全体・シーンの読みは null
    scene_id: str | None = None        # シーンだけの読みのとき、そのシーン（#73）
    surface: str
    reading: str
    updated_at: UtcDatetime

    model_config = ConfigDict(from_attributes=True)


class ReadingSpanRead(BaseModel):
    surface: str
    reading: str
    source: str        # ruby / project / global / ai
    start: int         # text の中の位置
    end: int
    src_start: int     # ナレーション本文の中の位置
    src_end: int


class ReadingGuessRequest(BaseModel):
    surface: str = Field(..., min_length=1, max_length=50)


class ReadingGuessRead(BaseModel):
    surface: str
    reading: str
    source: str        # scene / project / global / ai（辞書・AI にある）/ guess（推定）


class MarkupInspectRequest(BaseModel):
    text: str = Field(default="", max_length=20000)


class MarkupProblemRead(BaseModel):
    line: int
    column: int
    message: str


class MarkupInspectRead(BaseModel):
    normalized: str            # 表記ゆれをそろえた本文（保存時にはこの形になる）
    plain_length: int          # 記号を除いた文字数（画面の「◯文字」用）
    problems: list[MarkupProblemRead]


class SceneReadingRead(BaseModel):
    text: str                  # TTS に渡す読み上げ用テキスト
    ai_checked: bool           # AI の確認が今のナレーションに対して済んでいるか
    spans: list[ReadingSpanRead]
