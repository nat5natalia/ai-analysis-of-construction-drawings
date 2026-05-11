from pdf2image import convert_from_path
from PIL import Image
import os


def load_drawing(path: str):
    """
    Загружает PDF (все страницы) или изображение
    Возвращает список PIL Image объектов
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    path_lower = path.lower()

    if path_lower.endswith(".pdf"):
        images = convert_from_path(path)
        return images  

    elif path_lower.endswith((".jpg", ".jpeg", ".png", ".tiff", ".bmp")):
        return [Image.open(path)]

    else:
        raise ValueError(f"Unsupported format: {path}")