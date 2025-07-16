from pydantic import BaseModel, ConfigDict

from .roi_points_dto import RoiPointsDto


class RoiDto(BaseModel):
    roi: list[RoiPointsDto]
    model_config = ConfigDict(extra="ignore")