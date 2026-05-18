import numpy as np
from sentence_transformers import SentenceTransformer
from typing import List, Union

class EmbeddingGenerator:
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        local_model_path = "/app/models/transformers/all-MiniLM-L6-v2"
        try:
            # Сначала пробуем загрузить из локальной папки
            self.model = SentenceTransformer(local_model_path)
        except Exception:
            # Если не вышло (например, при запуске вне докера), пробуем по имени
            self.model = SentenceTransformer(model_name)

    def generate(self, text: str) -> List[float]:
        if not text or not text.strip():
            # Возвращаем нулевой вектор, если текст пуст
            return [0.0] * 384
        embedding = self.model.encode(text)
        return embedding.tolist()

    def batch_generate(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        embeddings = self.model.encode(texts)
        return embeddings.tolist()