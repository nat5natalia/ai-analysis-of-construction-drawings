"""
Модуль для взаимодействия с моделями Data Science.
Здесь должны быть реальные вызовы моделей (OpenAI, локальные и т.д.).
Пока оставлены заглушки.
"""

from pdf import file_to_images_base64
import os

def generate_description(file_path: str) -> str:
    """
    Генерирует описание чертежа с помощью мультимодальной LLM.
    """
    # Пример: преобразовать файл в base64 и отправить в GPT-4o
    images_base64 = file_to_images_base64(file_path)
    # TODO: реализовать вызов модели
    # ...
    return f"[DS] Описание чертежа {os.path.basename(file_path)}."

def answer_question(file_path: str, question: str) -> str:
    """
    Отвечает на вопрос по чертежу (RAG).
    """
    # TODO: реализовать RAG
    return f"[DS] Ответ на вопрос '{question}'."

def compute_embedding(text: str) -> list[float]:
    """
    Вычисляет эмбеддинг текста.
    """
    # Пример: использовать sentence-transformers или OpenAI
    # TODO: реализовать эмбеддинг
    return [0.0] * 384  # фиктивный вектор