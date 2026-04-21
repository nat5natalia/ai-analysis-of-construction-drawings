import cv2 
import numpy as np 
from PIL import Image 
from typing import List, Dict, Any 
import base64 
from io import BytesIO 
import logging 
logger = logging.getLogger(__name__)
from ultralytics import YOLO


class YOLODetector:
    def __init__(self, model_name: str='yolov8n.pt'):
        self.model_name = model_name 
        self.model = None 
        self._load_model()
    def _load_model(self):
        try:
            self.model = YOLO(self.model_name)
            logger.info(f'YOLO загружен')
        except Exception as e:
            logger.error(f'Ошибка {e}')
    def detect_from_base64(self, image_base64: str)->List[Dict]:
        if self.model is None:
            return []
        image_data = base64.b64decode(image_base64)
        nparr = np.frombuffer(image_data,np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return self.detect(img)
    def detect(self, image: np.ndarray)->List[Dict]:
        results = self.model(image)
        detected = []
        for result in results:
            if result.boxes is not None:
                for box in result.boxes:
                    obj = {
                        'class': result.names[int(box.cls[0])],
                        'confidence':float(box.conf[0]),
                        'bbox':box.xyxy[0].tolist(),
                        'center': [
                            (box.xyxy[0][0] + box.xyxy[0][2]) / 2,
                            (box.xyxy[0][1] + box.xyxy[0][3])/2
                        ]
                    }
                    detected.append(obj)
            return detected 
    def detect_drawing_elements(self, image_base64: str)-> Dict:
        objects = self.detect_from_base64(image_base64)
        result = {
            "dimension_lines": [],
            "text_blocks": [],
            "tables": [],
            "symbols": [],
            "other": []
        }
        for obj in objects:
            class_name = obj["class"].lower()
            if "line" in class_name or "arrow" in class_name:
                result["dimension_lines"].append(obj)
            elif "table" in class_name or "grid" in class_name:
                result["tables"].append(obj)
            elif "text" in class_name or "character" in class_name:
                result["text_blocks"].append(obj)
            elif "symbol" in class_name:
                result["symbols"].append(obj)
            else:
                result["other"].append(obj)
        return result 

_yolo = None

def get_yolo():
    global _yolo
    if _yolo is None:
        _yolo = YOLODetector()
    return _yolo