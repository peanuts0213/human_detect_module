from pydantic import BaseModel

from ...module_manage.roi_dto import RoiDto


class RequestPutConfigDto(BaseModel):
    iou: float
    conf: float
    imgsz: int
    roiList: list[RoiDto]
    isActivate: bool