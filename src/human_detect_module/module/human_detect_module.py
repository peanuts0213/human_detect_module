from datetime import datetime
import os
from queue import Queue, Empty
from asyncio import Queue as AsyncQueue
from threading import Thread, Event
from typing import Any
import cv2
from cv2.typing import MatLike
from ..module.socket_client import SocketClient
import ray
from ultralytics import YOLO #type: ignore

from ..dto.socket.result_dto import ResultDto
from ..dto.module_manage.request.request_put_config_dto import (
    RequestPutConfigDto
)
from ..dto.module_manage.request.request_module_manage_dto import (
    RequestModuleManageDto
)
from ..module.frame_reader import FrameReader
from ..module.human_detector import HumanDetector
from ..module.visualizer import Visualizer
from ..module.webrtc_publisher import WebRTCPublisher

@ray.remote(num_cpus=0, num_gpus=0.25)
class HumanDetectModule:
  def __init__(
    self,
    base_address: str,
    sfu_address: str,
    turn_address: str,
    dto: RequestModuleManageDto,
    yolo_model: YOLO,
  ):
    """
      frame reader를 사용해 Gstreamer를 통한 RTSP 스트림 read
      human detector를 통해 객체감지
      결과를 human detect producer를 통해 produce하고
      visualize를 통해 stream을 위한 프레임 생성
      shared 메모리에 담아 stream service에서 streamingResponse로 사용
    """
    # Request Values
    self.base_address = base_address
    self.cctv_id = dto.cctvId
    self.rtsp_url = dto.rtspUrl
    self.iou = dto.iou
    self.conf = dto.conf
    self.imgsz = dto.imgsz
    self.roi_list = dto.roiList
    self.isAtivate = dto.isActivate
    # YOLO
    self.yolo_model = yolo_model
    
    # Thread
    self.run_thread: Thread | None = None
    self.read_thread: Thread | None = None
    
    # Flag for Process Control
    self.running = False
    self.stop_event: Event = Event()
    
    # from Reader and Publisher to Run Frame Queue
    self.frame_queue: Queue[MatLike | None] = Queue(maxsize=5)
    self.latest_frame: MatLike | None = None
    self.publisher_frame_queue: AsyncQueue[MatLike | None] = AsyncQueue(maxsize=5)
    
    # Human Detect Result for Visualize
    self.results: list[dict[str, Any]] | None | list[None] = None
    
    # Frame for Stream
    self.frame_shape: tuple[int, int, int] = (1080, 1920, 3)

    # Helpers
    self.frame_reader = FrameReader(
      self.rtsp_url, 
      self.frame_queue, 
      self.frame_shape, 
      self.stop_event
    )
    self.webrtc_publisher = WebRTCPublisher(
      self.publisher_frame_queue, 
      self.cctv_id,
      sfu_address,
      turn_address
    )  
    self.human_detector = HumanDetector(self.yolo_model, self.roi_list)
    self.visualizer = Visualizer()
    self.socket_client = SocketClient(self.cctv_id)
    
  def start(self):
    print("start",flush=True)
    if self.stop_event.is_set():
      self.stop_event.clear()
    if self.running:
      return
    self.running = True
    
    if self.run_thread is None or not self.run_thread.is_alive():
      
      self.read_thread = Thread(target=self.frame_reader.read, daemon=True)
      self.run_thread = Thread(target=self.run, daemon=True)
      
      self.read_thread.start()
      self.run_thread.start()


  def stop(self):
    print("stop",flush=True)
    self.stop_event.set()
    if self.read_thread and self.read_thread.is_alive():
      self.read_thread.join(timeout=2)
    if self.run_thread and self.run_thread.is_alive():
      self.run_thread.join(timeout=2)

  def run(self):
    try:
      while not self.stop_event.is_set():
        try:
          frame: MatLike | None = self.frame_queue.get(timeout=2)
          if frame is None:
            break
        except Empty:
          print("Queue is empty, skipping frame", flush=True)
          continue
        frame_copy = frame.copy() if not frame.flags['WRITEABLE'] else frame
        
        if self.isAtivate :
          self.results = self.human_detector.detect(
            frame, 
            self.iou, 
            self.conf, 
            self.imgsz
          )
          if len(self.results) > 0:
            result_list_dto:list[ResultDto] = []
            for obj in self.results:
              if obj['id'] is None or obj['prob'] is None:
                continue
              result_dto=ResultDto(
                xyxy=obj['xyxy'],
                id=obj['id'],
                prob=obj['prob']
              )
              result_list_dto.append(result_dto)
              
            self.socket_client.send_human_detect_event(self.cctv_id, result_list_dto)
            self.visualizer.draw_bounding_boxes(frame_copy, self.results)
            self.latest_frame = frame_copy.copy()
            
        if frame.shape != self.frame_shape:
          frame_copy = cv2.resize(
            frame_copy,
            (self.frame_shape[1], self.frame_shape[0]),
            interpolation=cv2.INTER_LANCZOS4
          )

        self.webrtc_publisher.put_frame_to_queue(frame_copy)
        print(f"✅ Frame pushed to WebRTC Queue for CCTV {self.cctv_id}", flush=True)  
        
    except Exception as error:
      print(f"Error in run: {error}",flush=True)
      
    finally:
      print("Run thread exiting",flush=True)
      self.cleanup()

  def cleanup(self):
    """ 리소스 해제 Method """
    # clean up shared memory
    errors = []
    try:
        self.socket_client.close()
    except Exception as e:
        print(f"SocketClient close error: {e}",flush=True)
        errors.append(e)
    try:
        self.webrtc_publisher.close()
    except Exception as e:
        print(f"WebRTCPublisher close error: {e}",flush=True)
        errors.append(e)

    self.running = False
    if self.stop_event.is_set():
      self.stop_event.clear()
    
    # 리소스 해제
    self.results = None
    self.latest_frame = None
    
    try:
        while not self.frame_queue.empty():
            self.frame_queue.get_nowait()
        while not self.publisher_frame_queue.empty():
            self.publisher_frame_queue.get_nowait()
        self.frame_queue.put(None)
        self.webrtc_publisher.put_frame_to_queue(None)
    except Exception as e:
        print(f"Queue cleanup error: {e}",flush=True)
        errors.append(e)
    print(f"{self.cctv_id} CCTV Human Detect Module resources cleaned up", flush=True)
    if errors:
        print(f"Cleanup finished with {len(errors)} errors.",flush=True)

  def update_config(self, dto: RequestPutConfigDto):
    self.isAtivate = dto.isActivate
    self.human_detector.update_config(dto)
    
  def save_frame(self, prefix: str = "manual") -> str | None:
    """외부 호출로 마지막 처리된 프레임을 저장하고 경로 반환"""
    if self.latest_frame is None:
        print("⚠️ No processed frame available to save.", flush=True)
        return None

    os.makedirs("saved_frames", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"saved_frames/{prefix}_{self.cctv_id}_{timestamp}.jpg"
    try:
        cv2.imwrite(filename, self.latest_frame)
        print(f"📸 [external] Frame saved to {filename}", flush=True)
        return f"http://{self.base_address}/human-detect-module/{filename}"
    except Exception as e:
        print(f"❌ [external] Failed to save frame: {e}", flush=True)
        return None
  