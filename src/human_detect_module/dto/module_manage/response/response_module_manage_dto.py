from pydantic import BaseModel


class ResponseModuleManageDto(BaseModel):
    isSuccess: bool
    cctvIdListOfRunningActor: list[int]
    