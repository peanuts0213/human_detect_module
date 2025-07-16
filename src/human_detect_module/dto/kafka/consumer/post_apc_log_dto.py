from pydantic import BaseModel, ConfigDict


class PostApcLogDto(BaseModel):
  cctvId: int
  logId: int
  isIn: bool
  model_config = ConfigDict(extra="ignore")