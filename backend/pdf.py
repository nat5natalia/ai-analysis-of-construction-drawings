import fitz  # PyMuPDF
import base64
import os


def pdf_to_images_base64(file_path: str) -> list[str]:
    """
    Конвертирует PDF в список base64-изображений (по одному на страницу).
    Base64 — это текстовое представление картинки, которое можно отправить в LLM.
    """
    doc = fitz.open(file_path)
    images = []

    for page in doc:
        # Рендерим страницу в изображение (150 dpi — оптимально для LLM)
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        images.append(base64.b64encode(img_bytes).decode())

    doc.close()
    return images


def image_to_base64(file_path: str) -> str:
    """
    Конвертирует PNG/JPEG в base64.
    Для картинок конвертация не нужна — просто читаем и кодируем.
    """
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def file_to_images_base64(file_path: str) -> list[str]:
    """
    Универсальная функция — сама определяет PDF или картинка.
    Возвращает список base64-строк (у картинки всегда один элемент).
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return pdf_to_images_base64(file_path)
    elif ext in [".png", ".jpg", ".jpeg", ".tiff", ".tif"]:
        return [image_to_base64(file_path)]
    else:
        raise ValueError(f"Неподдерживаемый формат: {ext}")
