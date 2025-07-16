import ray
import ray.actor
from ultralytics import YOLO

from ..dto.kafka.producer.saved_apc_frame_dto import SavedApcFrameDto  # type: ignore

from ..dto.kafka.consumer.change_human_detect_data_dto import ChangeHumanDetectDataDto  # type: ignore

from ..dto.module_manage.request.request_put_config_dto import(
    RequestPutConfigDto
)
from ..dto.module_manage.request.request_module_manage_dto import(
    RequestModuleManageDto,
)
from ..dto.module_manage.response.response_module_manage_dto import(
    ResponseModuleManageDto
)
from ..module.human_detect_module import(
    HumanDetectModule
)


class ModuleManageService:
    def __init__(
        self, 
        yolo_model: YOLO,
        actors_dict: dict[int, ray.actor.ActorHandle],
        base_address:str,
        sfu_address:str,
        turn_address:str
    ):
        self.yolo_model = yolo_model
        self.actors_dict = actors_dict
        self.base_address = base_address
        self.sfu_address = sfu_address
        self.turn_address = turn_address
        
    async def start_module(
        self, 
        req: RequestModuleManageDto
    ) -> ResponseModuleManageDto:
        cctv_id = req.cctvId
        if cctv_id in self.actors_dict:
            return ResponseModuleManageDto(
                isSuccess=False, 
                cctvIdListOfRunningActor=[
                    key_list for 
                    key_list in 
                    self.actors_dict
                ]
            ) 
        actor: ray.actor.ActorHandle = HumanDetectModule.remote(
            self.base_address,
            self.sfu_address,
            self.turn_address,
            req, 
            self.yolo_model,
        ) #type: ignore
        actor.start.remote() #type: ignore
        self.actors_dict[cctv_id] = actor 
        
        return ResponseModuleManageDto(
            isSuccess=True, 
            cctvIdListOfRunningActor=[
                key_list for 
                key_list in 
                self.actors_dict
            ]
        )
        
    async def stop_module(
        self, 
        cctv_id: int
    ) -> ResponseModuleManageDto:
        if cctv_id in self.actors_dict:
            actor = self.actors_dict[cctv_id]
            actor.stop.remote() #type: ignore
            ray.kill(actor) #type: ignore
            del self.actors_dict[cctv_id]
            return ResponseModuleManageDto(
                isSuccess=True, 
                cctvIdListOfRunningActor=[
                    key_list for 
                    key_list in 
                    self.actors_dict
                ]
            )
        return ResponseModuleManageDto(
            isSuccess=False, 
            cctvIdListOfRunningActor=[
                key_list for 
                key_list in 
                self.actors_dict
            ]
        )

    def update_config(
        self, 
        cctv_id: int,
        req: RequestPutConfigDto
    ) -> ResponseModuleManageDto:
        actor = self.actors_dict[cctv_id]
        actor.update_config.remote(req) # type: ignore
        return ResponseModuleManageDto(
            isSuccess=True, 
            cctvIdListOfRunningActor=[
                key_list for 
                key_list in 
                self.actors_dict
            ]
        )
    
    def save_frame(
        self,
        cctv_id: int, 
        logId: int,
        prefix: str
    ) -> SavedApcFrameDto:
        if cctv_id not in self.actors_dict:
            raise ValueError(f"CCTV ID {cctv_id} not found in running modules.")
        actor = self.actors_dict[cctv_id]
        path: str = ray.get(actor.save_frame.remote(prefix))
        if path is None:
            raise RuntimeError(f"Failed to save frame for CCTV {cctv_id}")
        return SavedApcFrameDto(
            id=logId,
            path=path
        )

    async def apply_human_detect_data(self, data: ChangeHumanDetectDataDto):
        for config in data.humanDetectConfigListDto:
            cctv_id = config.cctvId
            
            if cctv_id in self.actors_dict:
                self.update_config(
                    cctv_id,
                    RequestPutConfigDto(
                        iou=config.iou,
                        conf=config.conf,
                        imgsz=config.imgsz,
                        roiList=config.roiList,
                        isActivate=config.isActivate
                    )
                )
                print(
                    f"CCTV {cctv_id}is updated.", flush=True
                )
                
            else:
                await self.start_module(
                    RequestModuleManageDto(
                        cctvId=cctv_id,
                        rtspUrl=config.rtspUrl,
                        isActivate=config.isActivate,
                        iou=config.iou,
                        conf=config.conf,
                        imgsz=config.imgsz,
                        roiList=config.roiList
                    )
                )
                print(f"CCTV {cctv_id}is start", flush=True)