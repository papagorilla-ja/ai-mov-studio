from pydantic import BaseModel, ConfigDict

from core.clock import UtcDatetime

class SpeakerBase(BaseModel):
    name: str
    description: str | None = None
    reference_audio_path: str
    language: str = "ja"
    is_system: bool = False

class SpeakerCreate(SpeakerBase):
    pass

class SpeakerRead(SpeakerBase):
    id: str
    avatar_path: str | None = None
    created_at: UtcDatetime

    model_config = ConfigDict(from_attributes=True)

class SpeakerUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    language: str | None = None
    avatar_path: str | None = None
