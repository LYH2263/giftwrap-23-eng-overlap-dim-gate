from pydantic import BaseModel, Field


class BoxDimensions(BaseModel):
    length: float = Field(gt=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
