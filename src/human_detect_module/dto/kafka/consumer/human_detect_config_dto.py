from pydantic import BaseModel, ConfigDict
from typing import List
from ...module_manage.roi_dto import RoiDto

class HumanDetectConfigDto(BaseModel):
    rtspUrl: str
    isActivate: bool
    cctvId: int
    conf: float
    iou: float
    imgsz: int
    roiList: List[RoiDto]
    
    model_config = ConfigDict(extra="ignore")
    