import os
import numpy as np
import faiss
import json
import logging
from typing import List, Tuple, Dict

logger = logging.getLogger(__name__)


class VectorDB:
    def __init__(self, index_path: str = "data/faiss_index.bin", metadata_path: str = "data/faiss_metadata.json"):
        # Исправляем пути для Docker окружения
        self.index_path = os.path.abspath(index_path)
        self.metadata_path = os.path.abspath(metadata_path)

        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)

        self.index = None
        # Теперь храним список словарей с метаданными
        self.metadata: List[Dict] = []
        self._load_or_create()

    def _load_or_create(self):
        """Загружает существующий индекс или инициализирует пустой."""
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            try:
                self.index = faiss.read_index(self.index_path)
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
                logger.info(f"Загружен FAISS индекс: {self.index.ntotal} векторов")
            except Exception as e:
                logger.error(f"Ошибка загрузки индекса: {e}. Создаем новый.")
                self._reset_state()
        else:
            self._reset_state()

    def _reset_state(self):
        self.index = None
        self.metadata = []

    def add(self, text: str, embedding: List[float], drawing_id: str):
        """
        Добавляет вектор с привязкой к конкретному чертежу.
        drawing_id: уникальный идентификатор (например, md5 пути файла).
        """
        # Проверка на дубликаты в рамках одного чертежа, чтобы не раздувать индекс
        if any(m['text'] == text and m['drawing_id'] == drawing_id for m in self.metadata):
            return

        vec = np.array(embedding, dtype=np.float32).reshape(1, -1)
        faiss.normalize_L2(vec)

        if self.index is None:
            dimension = vec.shape[1]
            # IndexFlatIP (Inner Product) на нормализованных векторах = Cosine Similarity
            self.index = faiss.IndexFlatIP(dimension)
            logger.info(f"Инициализирован FAISS индекс. Размерность: {dimension}")

        self.index.add(vec)
        self.metadata.append({
            "text": text,
            "drawing_id": drawing_id
        })
        self._save()

    def _save(self):
        """Сохранение индекса и метаданных."""
        if self.index is not None:
            try:
                faiss.write_index(self.index, self.index_path)
                with open(self.metadata_path, "w", encoding="utf-8") as f:
                    json.dump(self.metadata, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Ошибка сохранения VectorDB: {e}")

    def search(self, query_embedding: List[float], drawing_id: str, k: int = 5) -> List[Tuple[str, float]]:
        """
        Поиск ближайших соседей ТОЛЬКО для конкретного чертежа.
        """
        if self.index is None or self.index.ntotal == 0:
            return []

        vec = np.array(query_embedding, dtype=np.float32).reshape(1, -1)
        faiss.normalize_L2(vec)

        # FAISS не поддерживает нативную фильтрацию в IndexFlatIP без доп. структур.
        # Поэтому берем чуть больше результатов (k*4) и фильтруем вручную по drawing_id.
        search_k = min(k * 4, self.index.ntotal)
        distances, indices = self.index.search(vec, search_k)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx != -1 and idx < len(self.metadata):
                meta = self.metadata[idx]
                if meta['drawing_id'] == drawing_id:
                    results.append((meta['text'], float(dist)))

            if len(results) >= k:
                break

        return results

    def clear_drawing(self, drawing_id: str):
        """Удаляет данные конкретного чертежа (требует полной перезаписи индекса)."""
        if not self.metadata:
            return

        # Находим индексы, которые НЕ относятся к этому чертежу
        keep_indices = [i for i, m in enumerate(self.metadata) if m['drawing_id'] != drawing_id]

        if len(keep_indices) == len(self.metadata):
            return

        if not keep_indices:
            self.clear_all()
            return

        # Пересоздаем индекс только с нужными векторами
        new_metadata = [self.metadata[i] for i in keep_indices]

        # Извлекаем векторы из старого индекса (только для Flat индекса!)
        old_vectors = []
        for i in keep_indices:
            old_vectors.append(self.index.reconstruct(i))

        new_index = faiss.IndexFlatIP(self.index.d)
        new_index.add(np.array(old_vectors).astype('float32'))

        self.index = new_index
        self.metadata = new_metadata
        self._save()
        logger.info(f"Данные чертежа {drawing_id} удалены.")

    def clear_all(self):
        """Полная очистка базы."""
        self._reset_state()
        if os.path.exists(self.index_path): os.remove(self.index_path)
        if os.path.exists(self.metadata_path): os.remove(self.metadata_path)
        logger.info("VectorDB полностью очищена.")