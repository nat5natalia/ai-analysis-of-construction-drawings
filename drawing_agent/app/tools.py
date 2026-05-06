import base64
import re
import numpy as np
import cv2
from io import BytesIO
from PIL import Image
from langchain_core.tools import tool
import easyocr
import logging 
from .yolo import get_yolo
logger = logging.getLogger(__name__)
_current_drawing = None
_ocr_reader = None

def get_ocr_reader():
    """Ленивая инициализация EasyOCR"""
    global _ocr_reader
    if _ocr_reader is None:
        _ocr_reader = easyocr.Reader(['ru', 'en'], gpu=False)
    return _ocr_reader

def set_current_drawing(drawing_base64: str):
    global _current_drawing
    _current_drawing = drawing_base64

def get_current_drawing() -> str:
    global _current_drawing
    return _current_drawing

@tool
def detect_yolo_objects() -> str:
    """Детекция"""
    image_base64 = get_current_drawing()
    yolo = get_yolo()
    result = yolo.detect_drawing_elements(image_base64)
    output = f"""
    === YOLO ДЕТЕКЦИЯ ===
    Размерные линии: {len(result['dimension_lines'])}
    Таблицы: {len(result['tables'])}
    Текстовые блоки: {len(result['text_blocks'])}
    Символы: {len(result['symbols'])}
    """ 
    return output

@tool
def find_dimension_lines()->str:
    """Линии"""
    image_base64 = get_current_drawing()
    yolo = get_yolo()
    result = yolo.detect_drawing_elements(image_base64)
    if not result['dimension_lines']:
        return "Размерные линии не найдены"
    
    lines_info = []
    for i, line in enumerate(result['dimension_lines'][:5]):
        lines_info.append(
            f"Линия {i+1}: центр ({line['center'][0]:.0f}, {line['center'][1]:.0f}), "
            f"уверенность {line['confidence']:.2f}"
        )
    
    return f"Найдено размерных линий: {len(result['dimension_lines'])}\n" + "\n".join(lines_info)

@tool
def extract_text(image_base64: str = None) -> str:
    """Извлекает текст с чертежа с помощью EasyOCR"""
    img_base64 = image_base64 or get_current_drawing()
    if not img_base64:
        return "Ошибка: чертеж не загружен"
    try:
        image_data = base64.b64decode(img_base64)
        image = Image.open(BytesIO(image_data))
        
        reader = get_ocr_reader()
        result = reader.readtext(np.array(image))
        
        texts = []
        for (bbox, text, confidence) in result:
            if confidence > 0.4:
                texts.append(f"{text}")
        
        if not texts:
            return "На чертеже не удалось распознать текст"
        
        return "\n".join(texts)
        
    except Exception as e:
        logger.error(f"Ошибка OCR: {str(e)}")
        return f"Ошибка OCR: {str(e)}"

@tool
def extract_dimensions() -> str:
    """Извлекает размерные линии с чертежа с помощью OpenCV"""
    
    image_base64 = get_current_drawing()
    
    if not image_base64:
        return "Ошибка: чертеж не загружен"
    
    try:
        image_data = base64.b64decode(image_base64)
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        
        edges = cv2.Canny(img, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, 100, minLineLength=100, maxLineGap=10)
        
        if lines is None:
            return "Не удалось найти размерные линии"
        
        horizontal_lines = []
        vertical_lines = []
        
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if abs(y2 - y1) < 10:
                horizontal_lines.append(abs(x2 - x1))
            elif abs(x2 - x1) < 10:
                vertical_lines.append(abs(y2 - y1))
        
        width_px = max(horizontal_lines) if horizontal_lines else 0
        height_px = max(vertical_lines) if vertical_lines else 0
        
        scale = 0.1  
        
        return f"""- Ширина: {width_px * scale:.1f} мм
- Высота: {height_px * scale:.1f} мм
- Количество линий: {len(lines)}"""
        
    except Exception as e:
        logger.error(f"Ошибка извлечения размеров: {str(e)}")
        return f"Ошибка извлечения размеров: {str(e)}"

@tool
def detect_holes() -> str:
    """Находит отверстия на чертеже с помощью Hough Circle Transform"""
    image_base64 = get_current_drawing()
    
    if not image_base64:
        return "Ошибка: чертеж не загружен"
    
    try:
        image_data = base64.b64decode(image_base64)
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        circles = cv2.HoughCircles(
            gray, 
            cv2.HOUGH_GRADIENT, 
            dp=1, 
            minDist=50,
            param1=50, 
            param2=30, 
            minRadius=10, 
            maxRadius=50
        )
        
        if circles is None:
            return "Отверстия не обнаружены"
        
        circles = np.round(circles[0, :]).astype(int)
        
        result = f"Обнаружено отверстий: {len(circles)}\n\n"
        for i, (x, y, r) in enumerate(circles, 1):
            result += f"Отверстие {i}: центр ({x}, {y}), радиус {r} пикселей\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка обнаружения отверстий: {str(e)}")
        return f"Ошибка обнаружения отверстий: {str(e)}"

@tool
def detect_tables() -> str:
    """Распознавание таблиц (спецификации, ведомости)"""
    image_base64 = get_current_drawing()
    
    if not image_base64:
        return "Ошибка: чертеж не загружен"
    try:
        image_data = base64.b64decode(image_base64)
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        
        reader = get_ocr_reader()
        result = reader.readtext(gray, paragraph=False)
        
        if not result:
            return "Текст на чертеже не найден"
        
        y_threshold = 30
        sorted_blocks = sorted(result, key=lambda x: (x[0][0][1], x[0][0][0]))
        
        rows = []
        current_row = []
        current_y = None
        
        for (bbox, text, confidence) in sorted_blocks:
            if confidence < 0.5:
                continue
            
            y_center = (bbox[0][1] + bbox[2][1]) // 2
            
            if current_y is None or abs(y_center - current_y) < y_threshold:
                current_row.append(text)
                current_y = y_center if current_y is None else current_y
            else:
                if current_row:
                    rows.append(current_row)
                current_row = [text]
                current_y = y_center
        
        if current_row:
            rows.append(current_row)
        
        if len(rows) < 2:
            return "Обнаружены текстовые блоки, но структура не похожа на таблицу"
        
        result_text = f"ОБНАРУЖЕНА ТАБЛИЦА: {len(rows)} строк\n\n"
        for i, row in enumerate(rows, 1):
            result_text += f"Строка {i}: " + " | ".join(row) + "\n"
        
        return result_text
        
    except Exception as e:
        logger.error(f"Ошибка распознавания таблиц: {str(e)}")
        return f"Ошибка распознавания таблиц: {str(e)}"

@tool
def extract_dims(text: str) -> str:
    """Извлекает размеры из текста (например: Ø25, 100мм)"""
    if not text:
        return "Текст не предоставлен"
    
    pattern = r"(Ø?\d+\.?\d*)\s?(мм|mm|cm|м|m)?"
    matches = re.findall(pattern, text, re.IGNORECASE)
    
    if not matches:
        return "Размеры не найдены"
    
    result = "Найденные размеры:\n"
    for value, unit in matches:
        unit_display = unit if unit else "мм"
        result += f"- {value} {unit_display}\n"
    return result


@tool
def detect_objects(text: str) -> str:
    """Определяет объекты чертежа из текста"""
    if not text:
        return "Текст не предоставлен"
    
    objects = []
    text_lower = text.lower()
    
    if "отверсти" in text_lower or "hole" in text_lower or "Ø" in text:
        objects.append("отверстия")
    if "размер" in text_lower or "dimension" in text_lower:
        objects.append("размеры")
    if "лини" in text_lower or "line" in text_lower:
        objects.append("линии")
    if "таблиц" in text_lower or "table" in text_lower:
        objects.append("таблицы")
    if "обозначени" in text_lower or "symbol" in text_lower:
        objects.append("обозначения")
    
    if not objects:
        return "Объекты не обнаружены"
    
    return f"Обнаруженные объекты: {', '.join(objects)}"
@tool
def get_drawing_metadata() -> str:
    """Возвращает метаданные чертежа"""
    return "Метаданные будут получены из состояния"


ALL_TOOLS = [
    extract_text,
    extract_dimensions,
    detect_holes,
    detect_tables,
    extract_dims,
    detect_objects,
    get_drawing_metadata,
    detect_yolo_objects,  
    find_dimension_lines, 
]

print(f" Зарегистрировано инструментов: {len(ALL_TOOLS)}")
for t in ALL_TOOLS:
    print(f"   - {t.name}: {t.description[:50]}")