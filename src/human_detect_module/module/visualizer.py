import cv2
from cv2.typing import MatLike
from typing import Any

class Visualizer:
  def draw_bounding_boxes(
    self, 
    frame: MatLike, 
    objects: list[dict[str, Any]] | list[None]
  ):
    for obj in objects:
      if obj is None:
        print("Found None in objects")
        continue
      x1, y1, x2, y2 = obj["xyxy"]
      obj_id = obj["id"]
      prob = obj["prob"]
      
      cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
      text = f"ID:{obj_id} Conf:{prob:.2f}" \
      if obj_id is not None \
      else f"Conf:{prob:.2f}"
      font_scale = 0.8
      font_thickness = 2
      font = cv2.FONT_HERSHEY_SIMPLEX
      
      (text_width, text_height), baseline = cv2.getTextSize(
        text, 
        font, 
        font_scale, 
        font_thickness
      )
      text_x = x1
      text_y = max(y1 - 10, text_height + baseline)
      
      bg_color = (50, 50, 50)
      alpha = 0.7
      overlay = frame.copy()
      cv2.rectangle(
        overlay,
        (text_x, text_y - text_height - baseline),
        (text_x + text_width, text_y + baseline),
        bg_color,
        -1
      )
      cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
      
      cv2.putText(
        frame,
        text,
        (text_x, text_y),
        font,
        font_scale,
        (0, 255, 0),
        font_thickness,
        cv2.LINE_AA
      )