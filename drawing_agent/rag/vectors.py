import os
import faiss
import numpy as np
import pickle
from typing import List, Dict, Any, Optional


class VectorDB:
    """
    Постоянное векторное хранилище.
    Поддерживает произвольные ID, удаление и сохранение на диск.
    """

    def __init__(self, dimension: int = 384, save_dir: str = "storage/vector_db"):
        self.dimension = dimension
        self.save_dir = save_dir
        self.index_path = os.path.join(save_dir, "faiss.index")
        self.meta_path = os.path.join(save_dir, "metadata.pkl")

        os.makedirs(save_dir, exist_ok=True)

        self.index = None
        self.metadata: Dict[int, Dict[str, Any]] = {}
        self._load_or_create()

    def _load_or_create(self):
        if os.path.exists(self.index_path) and os.path.exists(self.meta_path):
            try:
                self.index = faiss.read_index(self.index_path)
                with open(self.meta_path, "rb") as f:
                    self.metadata = pickle.load(f)
                return
            except Exception as e:
                print(f"Ошибка загрузки индекса: {e}. Создаем новый.")

        # Если файлов нет или ошибка — создаем новый
        base_index = faiss.IndexFlatIP(self.dimension)
        self.index = faiss.IndexIDMap(base_index)
        self.metadata = {}

    def _save(self):
        """Принудительное сохранение состояния на диск."""
        faiss.write_index(self.index, self.index_path)
        with open(self.meta_path, "wb") as f:
            pickle.dump(self.metadata, f)

    def add(self, vectors: np.ndarray, ids: List[int], metadata_list: List[Dict[str, Any]]):
        """Добавление векторов с сохранением."""
        vectors = vectors.astype('float32')
        if len(vectors.shape) == 1:
            vectors = vectors.reshape(1, -1)

        faiss.normalize_L2(vectors)
        self.index.add_with_ids(vectors, np.array(ids, dtype='int64'))

        for i, vec_id in enumerate(ids):
            self.metadata[int(vec_id)] = metadata_list[i]

        self._save()

    def search(self, query_vector: np.ndarray, k: int = 5) -> List[Dict[str, Any]]:
        if self.index.ntotal == 0:
            return []

        query_vector = query_vector.astype('float32').reshape(1, -1)
        faiss.normalize_L2(query_vector)

        distances, ids = self.index.search(query_vector, k)

        results = []
        for dist, idx in zip(distances[0], ids[0]):
            if idx == -1: continue
            results.append({
                'id': int(idx),
                'score': float(dist),
                'metadata': self.metadata.get(int(idx), {})
            })
        return results

    def delete(self, ids: List[int]):
        """Удаление векторов по ID и обновление файла."""
        if not ids: return

        id_array = np.array(ids, dtype='int64')
        self.index.remove_ids(id_array)

        for vid in ids:
            self.metadata.pop(int(vid), None)

        self._save()

    def count(self):
        return self.index.ntotal