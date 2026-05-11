import os
import json
import numpy as np
import faiss
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)

class VectorDB:
    """
    Простая обёртка над FAISS для хранения эмбеддингов.
    Сохраняет индекс на диск и метаданные (id -> drawing_id).
    """
    def __init__(self, index_path: str = "faiss_index.bin", metadata_path: str = "faiss_metadata.json"):
        self.index_path = index_path
        self.metadata_path = metadata_path
        self.index = None
        self.metadata = []  # список drawing_id в порядке добавления
        self._load_or_create()

    def _load_or_create(self):
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            try:
                self.index = faiss.read_index(self.index_path)
                with open(self.metadata_path, "r") as f:
                    self.metadata = json.load(f)
                logger.info("FAISS index and metadata loaded from disk")
            except Exception as e:
                logger.warning(f"Failed to load FAISS state ({e}), creating new index")
                self.index = faiss.IndexFlatIP(384)
                self.metadata = []
                self._save()
        else:
            # Создаём плоский индекс inner product (после нормализации даёт косинусное сходство)
            self.index = faiss.IndexFlatIP(384)  # размерность эмбеддинга 384
            self.metadata = []
            self._save()
            logger.info("FAISS index created (384-dimensional IP)")

    def _save(self):
        try:
            faiss.write_index(self.index, self.index_path)
            with open(self.metadata_path, "w") as f:
                json.dump(self.metadata, f)
            logger.debug("FAISS index and metadata saved")
        except Exception as e:
            logger.error(f"Failed to save FAISS state: {e}")

    def add(self, drawing_id: str, embedding: List[float]):
        """Добавляет эмбеддинг в индекс."""
        if len(embedding) != self.index.d:
            raise ValueError(f"Embedding dimension {len(embedding)} does not match index dimension {self.index.d}")
        vec = np.array(embedding, dtype=np.float32).reshape(1, -1)
        faiss.normalize_L2(vec)  # нормализуем для использования IP
        self.index.add(vec)
        self.metadata.append(drawing_id)
        self._save()
        logger.info(f"FAISS: added embedding for {drawing_id} (total: {self.index.ntotal})")

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
        logger.debug(f"FAISS search completed, top-{k} returned")
        return results

    def delete(self, drawing_id: str):
        """Удаляет все вхождения drawing_id из индекса (путём перестроения)."""
        if drawing_id not in self.metadata:
            logger.info(f"FAISS delete: {drawing_id} not in metadata, skipping")
            return

        indices_to_keep = [i for i, did in enumerate(self.metadata) if did != drawing_id]
        if not indices_to_keep:
            self.index.reset()
            self.metadata = []
            logger.info(f"FAISS delete: removed last remaining vector ({drawing_id})")
        else:
            old_vectors = self.index.reconstruct_n(0, self.index.ntotal)
            new_vectors = np.array([old_vectors[i] for i in indices_to_keep], dtype=np.float32)
            new_metadata = [self.metadata[i] for i in indices_to_keep]
            self.index = faiss.IndexFlatIP(self.index.d)
            if len(new_vectors) > 0:
                faiss.normalize_L2(new_vectors)
                self.index.add(new_vectors)
            self.metadata = new_metadata
            logger.info(f"FAISS delete: removed {drawing_id}, remaining {len(new_metadata)} vectors")
        self._save()

# Глобальный экземпляр
vector_db = VectorDB()