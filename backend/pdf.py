import fitz
import base64
import os
import logging

# Настройка логирования для модуля
logger = logging.getLogger(__name__)


def save_pdf_thumbnail(file_path: str, output_path: str):
    """
    Генерирует легкое изображение первой страницы PDF для быстрого предпросмотра.
    """
    try:
        if not os.path.exists(file_path):
            logger.error(f"Thumbnail error: File not found at {file_path}")
            return None

        doc = fitz.open(file_path)
        if len(doc) == 0:
            logger.warning(f"Thumbnail warning: PDF file is empty {file_path}")
            return None

        # Берем только первую страницу
        page = doc[0]
        # dpi=72 делает картинку маленькой и быстрой для загрузки в списке
        pix = page.get_pixmap(dpi=72)
        pix.save(output_path)
        doc.close()

        logger.info(f"Thumbnail successfully saved to {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Failed to generate thumbnail for {file_path}: {e}")
        return None


def pdf_to_images_base64(file_path: str) -> list[str]:
    """
    Конвертирует PDF в список base64-изображений (по одному на страницу).
    150 dpi — баланс между качеством для нейросети и размером данных.
    """
    try:
        doc = fitz.open(file_path)
        images = []

        for page in doc:
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            images.append(base64.b64encode(img_bytes).decode())

        doc.close()
        logger.info(f"Converted PDF {file_path} to {len(images)} base64 images")
        return images
    except Exception as e:
        logger.error(f"Error converting PDF to base64: {e}")
        return []


def image_to_base64(file_path: str) -> str:
    """
    Конвертирует PNG/JPEG в base64.
    """
    try:
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception as e:
        logger.error(f"Error converting image to base64 {file_path}: {e}")
        return ""


def file_to_images_base64(file_path: str) -> list[str]:
    """
    Универсальная функция для обработки чертежей любого формата.
    Возвращает список строк base64.
    """
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return []

    ext = os.path.splitext(file_path)[1].lower()
    logger.info(f"Processing file to base64. Extension: {ext}")

    if ext == ".pdf":
        return pdf_to_images_base64(file_path)
    elif ext in [".png", ".jpg", ".jpeg", ".tiff", ".tif", ".webp"]:
        return [image_to_base64(file_path)]
    else:
        logger.warning(f"Unsupported file format attempted: {ext}")
        raise ValueError(f"Неподдерживаемый формат: {ext}")