from pydantic import BaseModel, Field


class SettingsUpdate(BaseModel):
    overlap: float = Field(gt=0)
