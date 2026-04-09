import base64
from io import BytesIO
from PIL import Image
import numpy as np


def image_to_base64(image: Image.Image) -> str:
    """
    Конвертирует PIL → base64
    """

    buffer = BytesIO()
    image.save(buffer, format="PNG")

    return base64.b64encode(buffer.getvalue()).decode()


def prepare_image(image: Image.Image) -> Image.Image:
    """
    Базовая обработка изображения
    """

    # конвертация
    image = image.convert("RGB")

    # можно добавить resize если нужно
    max_size = 2000
    if max(image.size) > max_size:
        image.thumbnail((max_size, max_size))

    return image


def preprocess(image: Image.Image):
    """
    Главная функция preprocess
    """

    image = prepare_image(image)

    image_base64 = image_to_base64(image)

    return {
        "image_base64": image_base64,
        "ocr_text": "",   # заполняется позже tool'ом
    }