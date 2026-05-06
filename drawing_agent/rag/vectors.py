import os
import numpy as np
import faiss
import json
from typing import List, Tuple


class VectorDB:
    def __init__(self, index_path: str = "faiss_index.bin", metadata_path: str = "faiss_metadata.json"):
        self.index_path = index_path
        self.metadata_path = metadata_path
        self.index = None
        self.metadata = []
        self._load_or_create()

    def _load_or_create(self):
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            self.index = faiss.read_index(self.index_path)
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)
        else:
            # Мы НЕ создаем индекс сразу, так как не знаем размерность
            self.index = None
            self.metadata = []

    def add(self, text: str, embedding: List[float]):
        vec = np.array(embedding, dtype=np.float32).reshape(1, -1)
        faiss.normalize_L2(vec)

        # Если индекс еще не создан (первый запуск)
        if self.index is None:
            dimension = vec.shape[1]
            self.index = faiss.IndexFlatIP(dimension)
            print(f"Инициализирован FAISS индекс с размерностью: {dimension}")

        self.index.add(vec)
        self.metadata.append(text)
        self._save()

    def _save(self):
        if self.index is not None:
            faiss.write_index(self.index, self.index_path)
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)

    def search(self, query_embedding: List[float], k: int = 5) -> List[Tuple[str, float]]:
        if self.index is None or self.index.ntotal == 0:
            return []
        vec = np.array(query_embedding, dtype=np.float32).reshape(1, -1)
        faiss.normalize_L2(vec)
        distances, indices = self.index.search(vec, min(k, self.index.ntotal))
        return [(self.metadata[idx], float(dist)) for idx, dist in zip(indices[0], distances[0]) if idx != -1]