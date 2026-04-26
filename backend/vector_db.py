import faiss
import numpy as np
from typing import List, Dict, Any

class VectorDB:
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        # Базовый индекс для поиска по косинусному сходству (IP на нормализованных векторах)
        base_index = faiss.IndexFlatIP(dimension)
        # Оборачиваем, чтобы можно было присваивать ID и удалять
        self.index = faiss.IndexIDMap(base_index)
        # Маппинг internal_id -> вектор и метаданные
        self.vectors = {}  # internal_id: np.array
        self.metadata = {} # internal_id: dict

    def add(self, vectors: np.ndarray, ids: List[int], metadata_list: List[Dict[str, Any]]):
        """Добавление векторов с заданными ID (обычно это ObjectId из MongoDB)."""
        vectors = vectors.astype('float32')
        # faiss нормализует только при поиске, можно нормализовать здесь
        faiss.normalize_L2(vectors)
        self.index.add_with_ids(vectors, np.array(ids, dtype='int64'))
        for i, vec_id in enumerate(ids):
            self.vectors[vec_id] = vectors[i]
            self.metadata[vec_id] = metadata_list[i]

    def search(self, query_vector: np.ndarray, k: int = 5):
        query_vector = query_vector.astype('float32').reshape(1, -1)
        faiss.normalize_L2(query_vector)
        distances, ids = self.index.search(query_vector, k)
        results = []
        for dist, idx in zip(distances[0], ids[0]):
            if idx == -1:
                continue
            results.append({
                'id': int(idx),
                'score': float(dist),
                'metadata': self.metadata.get(int(idx), {})
            })
        return results

    def delete(self, ids: List[int]):
        """Удаление векторов по ID."""
        if not ids:
            return
        id_array = np.array(ids, dtype='int64')
        self.index.remove_ids(id_array)
        for vid in ids:
            self.vectors.pop(vid, None)
            self.metadata.pop(vid, None)

    def count(self):
        return self.index.ntotal