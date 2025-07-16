from pydantic import BaseModel

from ..roi_dto import RoiDto


class RequestModuleManageDto(BaseModel):
    cctvId: int
    rtspUrl: str
    isActivate: bool
    iou: float
    conf: float
    imgsz: int
    roiList: list[RoiDto]
