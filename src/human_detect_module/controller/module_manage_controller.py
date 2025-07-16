from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Body, Depends, Query

from ..containers.module_container import ModuleContainer
from ..dto.module_manage.request.request_put_config_dto import (
    RequestPutConfigDto,
)
from ..dto.module_manage.request.request_module_manage_dto import (
    RequestModuleManageDto,
)
from ..dto.module_manage.response.response_module_manage_dto import (
    ResponseModuleManageDto,
)
from ..service.module_manage_service import ModuleManageService

router = APIRouter(prefix="/api/modeul_manage", tags=["Module Manage"])


@router.post("/start/", response_model=ResponseModuleManageDto)
@inject
async def post_module_setup(
    req: RequestModuleManageDto, 
    service: ModuleManageService = Depends(
        Provide[ModuleContainer.module_manage_service]
    )
) -> ResponseModuleManageDto:
    return await service.start_module(req)

@router.delete("/stop/", response_model=ResponseModuleManageDto)
@inject
async def delete_module(
    cctv_id: int,
    service: ModuleManageService = Depends(
        Provide[ModuleContainer.module_manage_service]
    )
) -> ResponseModuleManageDto:
    return await service.stop_module(cctv_id)

@router.put("/config/", response_model=ResponseModuleManageDto)
@inject
def put_config(
    cctv_id: int = Query(),
    req: RequestPutConfigDto = Body(),
    service: ModuleManageService = Depends(
        Provide[ModuleContainer.module_manage_service]
    )
) -> ResponseModuleManageDto:
    return service.update_config(
        cctv_id=cctv_id,
        req=req
    )
