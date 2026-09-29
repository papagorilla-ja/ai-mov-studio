from pydantic import BaseModel, ConfigDict

from core.clock import UtcDatetime

class ProjectBase(BaseModel):
    name: str
    description: str | None = None

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None

class ProjectRead(ProjectBase):
    id: str
    video_count: int = 0
    created_at: UtcDatetime
    updated_at: UtcDatetime

    model_config = ConfigDict(from_attributes=True)


class ProjectImportRead(ProjectRead):
    """読み込みの結果。直した点があれば import_warnings で知らせる（#76）。"""
    import_warnings: list[str] = []
