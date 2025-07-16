from pydantic import BaseModel

class ResponseModuleManageListDto(BaseModel):
    cctvIdListRequestSuccess: list[int]
    cctvIdListRequestFail: list[int]
    cctvIdListOfRunningActor: list[int]
    