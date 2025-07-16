from pydantic import BaseModel, ConfigDict
from typing import List
from .human_detect_config_dto import HumanDetectConfigDto

class ChangeHumanDetectDataDto(BaseModel):
    humanDetectConfigListDto: List[HumanDetectConfigDto]
    
    model_config = ConfigDict(extra="ignore")