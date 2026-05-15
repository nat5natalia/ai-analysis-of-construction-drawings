from sentence_transformers import SentenceTransformer

import os

# Загружаем модель один раз – она будет кэшироваться в контейнере
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

def compute_embedding(text: str) -> list[float]:
    """Вычисляет эмбеддинг текста с помощью SentenceTransformer."""
    embedding = embedding_model.encode([text], show_progress_bar=False, convert_to_numpy=True)[0]
    return embedding.tolist()
