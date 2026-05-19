import cv2
import numpy as np
import base64
import logging
import threading
import os  # Добавлено для проверки путей
from io import BytesIO
from typing import List, Dict, Any, Optional
from ultralytics import YOLO
from .device import resolve_device

logger = logging.getLogger(__name__)

_yolo_lock = threading.Lock()
_yolo_instance: Optional['YOLODetector'] = None


class YOLODetector:
    # ИСПРАВЛЕНО: Указываем абсолютный путь внутри контейнера
    def __init__(self, model_path: str = '/app/models/best.pt'):
        """
        Инициализация детектора.
        :param model_path: Путь к весам YOLO внутри Docker (/app/models/best.pt)
        """
        self.model_path = model_path
        self.device = resolve_device()
        self.model = None
        self._load_model()

    def _load_model(self):
        try:
            # Проверяем, существует ли файл, прежде чем загружать
            if not os.path.exists(self.model_path):
                logger.error(f"Файл весов не найден по пути: {self.model_path}")
                raise FileNotFoundError(f"No such file: {self.model_path}")

            # Загрузка модели
            self.model = YOLO(self.model_path)
            logger.info(f"YOLO модель успешно загружена из {self.model_path}")
        except Exception as e:
            logger.error(f"Критическая ошибка при загрузке YOLO: {e}")

            # Fallback к базовой модели, если основная не найдена
            fallback_model = 'yolov8n.pt'
            if self.model_path != fallback_model:
                logger.warning(f"Попытка загрузки базовой модели {fallback_model}...")
                try:
                    # В Docker это может не сработать без интернета или прав,
                    # но как последний шанс оставляем
                    self.model = YOLO(fallback_model)
                except Exception as fe:
                    logger.error(f"Не удалось загрузить даже fallback модель: {fe}")

    def _prepare_image(self, image_base64: str) -> Optional[np.ndarray]:
        """Конвертирует base64 строку в OpenCV формат."""
        try:
            if "," in image_base64:
                image_base64 = image_base64.split(",")[1]

            image_data = base64.b64decode(image_base64)
            nparr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            return img
        except Exception as e:
            logger.error(f"Ошибка декодирования изображения: {e}")
            return None

    def detect(self, image: np.ndarray, conf_threshold: float = 0.25) -> List[Dict[str, Any]]:
        """Запуск инференса на изображении."""
        if self.model is None:
            logger.error("Инференс невозможен: модель не загружена")
            return []

        results = self.model.predict(
            image,
            conf=conf_threshold,
            verbose=False,
            device=self.device,
            half=self.device == "cuda",
        )
        detected = []

        for result in results:
            boxes = result.boxes
            for box in boxes:
                xyxy = box.xyxy[0].tolist()
                obj = {
                    'class': result.names[int(box.cls[0])],
                    'confidence': float(box.conf[0]),
                    'bbox': xyxy,
                    'center': [
                        (xyxy[0] + xyxy[2]) / 2,
                        (xyxy[1] + xyxy[3]) / 2
                    ],
                    'size': [
                        xyxy[2] - xyxy[0],
                        xyxy[3] - xyxy[1]
                    ]
                }
                detected.append(obj)
        return detected

    def detect_drawing_elements(self, image_base64: str) -> Dict[str, List[Dict[str, Any]]]:
        """Специализированный метод для чертежей."""
        img = self._prepare_image(image_base64)
        if img is None:
            return {"error": "Failed to decode image"}

        objects = self.detect(img)
        summary = {
            "dimension_lines": [],
            "text_blocks": [],
            "tables": [],
            "symbols": [],
            "other": []
        }

        for obj in objects:
            cls = obj["class"].lower()
            if any(k in cls for k in ["line", "dimension", "arrow"]):
                summary["dimension_lines"].append(obj)
            elif any(k in cls for k in ["table", "spec", "grid"]):
                summary["tables"].append(obj)
            elif any(k in cls for k in ["text", "stamp", "label"]):
                summary["text_blocks"].append(obj)
            elif any(k in cls for k in ["symbol", "circle", "hole", "mark"]):
                summary["symbols"].append(obj)
            else:
                summary["other"].append(obj)

        return summary


# ИСПРАВЛЕНО: Здесь тоже меняем дефолтный путь
def get_yolo(model_path: str = '/app/models/best.pt') -> YOLODetector:
    """Глобальная функция доступа (Thread-safe Singleton)."""
    global _yolo_instance
    with _yolo_lock:
        if _yolo_instance is None:
            _yolo_instance = YOLODetector(model_path=model_path)
    return _yolo_instance
