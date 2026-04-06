import os
import numpy as np
import faiss
from typing import List, Dict, Tuple
import pickle

class VectorDB:
    """
    Простая обёртка над FAISS для хранения эмбеддингов.
    Сохраняет индекс на диск и метаданные (id -> drawing_id).
    """
    def __init__(self, index_path: str = "faiss_index.bin", metadata_path: str = "faiss_metadata.pkl"):
        self.index_path = index_path
        self.metadata_path = metadata_path
        self.index = None
        self.metadata = []  # список drawing_id в порядке добавления
        self._load_or_create()

    def _load_or_create(self):
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            self.index = faiss.read_index(self.index_path)
            with open(self.metadata_path, "rb") as f:
                self.metadata = pickle.load(f)
        else:
            # Создаём плоский индекс inner product (после нормализации даёт косинусное сходство)
            self.index = faiss.IndexFlatIP(384)  # размерность эмбеддинга 384
            self.metadata = []
            self._save()

    def _save(self):
        faiss.write_index(self.index, self.index_path)
        with open(self.metadata_path, "wb") as f:
            pickle.dump(self.metadata, f)

    def add(self, drawing_id: str, embedding: List[float]):
        """Добавляет эмбеддинг в индекс."""
        vec = np.array(embedding, dtype=np.float32).reshape(1, -1)
        faiss.normalize_L2(vec)  # нормализуем для использования IP
        self.index.add(vec)
        self.metadata.append(drawing_id)
        self._save()

    def search(self, query_embedding: List[float], k: int = 10) -> List[Tuple[str, float]]:
        """Ищет k ближайших соседей, возвращает список (drawing_id, similarity)."""
        if self.index.ntotal == 0:
            return []
        vec = np.array(query_embedding, dtype=np.float32).reshape(1, -1)
        faiss.normalize_L2(vec)
        distances, indices = self.index.search(vec, min(k, self.index.ntotal))
        results = []
        for idx, dist in zip(indices[0], distances[0]):
            if idx != -1:
                results.append((self.metadata[idx], float(dist)))
        return results

    def delete(self, drawing_id: str):
        """Удаляет все вхождения drawing_id из индекса (перестраивает индекс)."""
        # Простой способ: пересоздать индекс без удаляемого
        # Но для этого нужны исходные эмбеддинги. Пока не реализуем.
        pass


# Глобальный экземпляр
vector_db = VectorDB()