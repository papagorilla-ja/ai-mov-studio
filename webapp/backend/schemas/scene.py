from pydantic import BaseModel, ConfigDict

from core.clock import UtcDatetime

class SceneBase(BaseModel):
    title: str | None = None
    layout_type: str = "text_only"
    slide_content_json: str | None = None
    narration_text: str | None = None
    outline_summary: str | None = None
    speaker_id: str | None = None
    speaker_b_id: str | None = None
    image_prompt: str | None = None
    # ナレーションの長さの上書き。None は「動画の既定に従う」。
    narration_length: str | None = None
    # ユーザーが見せ方を明示的に選んだか。False なら AI が選び直す。
    layout_pinned: bool = False

class SceneCreate(SceneBase):
    pass

class SceneUpdate(BaseModel):
    title: str | None = None
    layout_type: str | None = None
    slide_content_json: str | None = None
    narration_text: str | None = None
    outline_summary: str | None = None
    speaker_id: str | None = None
    speaker_b_id: str | None = None
    data_start: float | None = None
    data_duration: float | None = None
    custom_html: str | None = None
    custom_css: str | None = None
    image_prompt: str | None = None
    narration_length: str | None = None
    layout_pinned: bool | None = None

class SceneRead(SceneBase):
    id: str
    scenario_id: str
    index: int
    narration_audio_path: str | None = None
    narration_audio_duration: float | None = None
    # 音声が崩れている可能性があるときの文言（#57）。問題なければ null
    narration_audio_warning: str | None = None
    data_start: float | None = None
    data_duration: float | None = None
    custom_html: str | None = None
    custom_css: str | None = None
    image_prompt: str | None = None
    created_at: UtcDatetime
    updated_at: UtcDatetime

    model_config = ConfigDict(from_attributes=True)

class SceneReorder(BaseModel):
    new_index: int

class AiDesignAdjustRequest(BaseModel):
    instruction: str
