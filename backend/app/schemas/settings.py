from pydantic import BaseModel, Field


class OverlapUpdate(BaseModel):
    overlap: float = Field(gt=0)
