from typing import Any
import cv2
import numpy
from numpy.typing import NDArray
from cv2.typing import MatLike
from ultralytics import YOLO # type: ignore
from ultralytics.engine.results import Results # type: ignore

from ..dto.module_manage.request.request_put_config_dto \
import RequestPutConfigDto # type: ignore

from ..dto.module_manage.roi_dto import RoiDto # type: ignore

class HumanDetector:
    def __init__(self, yolo_model: YOLO, roi_list: list[RoiDto]):
        self.yolo_model = yolo_model
        self.roi_list = roi_list
        self.iou = 0.5  # 기본값
        self.conf = 0.25
        self.imgsz = 1920

    def detect( # type: ignore
      self, 
      frame: MatLike, 
      iou: float, 
      conf: float, 
      imgsz: int
    ):
        results = self.yolo_model.track( # type: ignore
            source=frame,
            classes=[0],
            persist=True,
            device=0,
            half=True,
            iou=iou,
            conf=conf,
            imgsz=imgsz,
            verbose=False,
            tracker="bytetrack.yaml"
        )
        if results and len(results) > 0:
            return self._filter_results_by_roi(results[0]) # type: ignore
        return [] # type: ignore

    def _filter_results_by_roi(self, result: Results): # type: ignore
        roi_polygons: list[NDArray[numpy.int32]] = []
        for roi_dto in self.roi_list:
            if len(roi_dto.roi) >= 3:
                roi_points = sorted(roi_dto.roi, key=lambda point: point.orderIndex)
                polygon_points = numpy.array(
                  [(p.x, p.y) for p in roi_points], 
                  dtype=numpy.int32
                )
                roi_polygons.append(polygon_points)

        if not roi_polygons:
            return [] # type: ignore

        filtered_objects: list[dict[str, Any]] = []
        if result.boxes is not None:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0]) # type: ignore
                box_center_x = (x1 + x2) / 2
                box_center_y = (y1 + y2) / 2
                for polygon in roi_polygons:
                    if cv2.pointPolygonTest(
                      polygon, 
                      (box_center_x, box_center_y), 
                      False
                    ) >= 0:
                        filtered_objects.append({
                            "xyxy": (x1, y1, x2, y2),
                            "id": int(
                              box.id[0].item() # type: ignore
                            ) if hasattr(
                              box, "id"
                            ) and box.id is not None else None, # type: ignore
                            "prob": float(
                              box.conf[0].item() # type: ignore
                            ) if hasattr(
                              box, "conf"
                            ) and box.conf is not None else None # type: ignore
                        })
                        break
                      
        return filtered_objects

    def update_config(self, dto: RequestPutConfigDto):
        self.iou = dto.iou
        self.conf = dto.conf
        self.imgsz = dto.imgsz
        self.roi_list = dto.roiList
        