from pydantic import BaseModel, ConfigDict

from core.clock import UtcDatetime

class VideoBase(BaseModel):
    name: str

class VideoCreate(VideoBase):
    pass

class VideoUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    duration_sec: float | None = None

class VideoRead(VideoBase):
    id: str
    project_id: str
    status: str
    output_dir: str | None = None
    duration_sec: float | None = None
    created_at: UtcDatetime
    updated_at: UtcDatetime

    model_config = ConfigDict(from_attributes=True)
