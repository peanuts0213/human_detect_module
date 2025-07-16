from pydantic import BaseModel


class SavedApcFrameDto(BaseModel):
  id: int
  path: str