from pydantic import BaseModel

class ResultDto(BaseModel):
  xyxy: list[int]
  id: int
  prob: float