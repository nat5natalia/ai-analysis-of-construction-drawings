"""
Модуль для взаимодействия с моделями Data Science.
Содержит реальные вызовы моделей (эмбеддинги через SentenceTransformer).
"""

from sentence_transformers import SentenceTransformer

import os

# Загружаем модель один раз – она будет кэшироваться в контейнере
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

def compute_embedding(text: str) -> list[float]:
    """Вычисляет эмбеддинг текста с помощью SentenceTransformer."""
    embedding = embedding_model.encode([text], show_progress_bar=False, convert_to_numpy=True)[0]
    return embedding.tolist()

def generate_description(file_path: str) -> str:
    """
    Генерирует описание чертежа с помощью мультимодальной LLM.
    (Пока заглушка, т.к. описание приходит от агента)
    """
    # В реальности здесь должен быть вызов LLM, но сейчас описание получаем через агента
    return "Описание будет получено от агента"

def answer_question(file_path: str, question: str) -> str:
    """
    Отвечает на вопрос по чертежу (RAG).
    (Пока заглушка, т.к. ответ приходит от агента)
    """
    return "Ответ будет получен от агента"
