import os
import numpy as np
import faiss
import json
import logging
from typing import List, Tuple, Dict, Optional

logger = logging.getLogger(__name__)


class VectorDB:
    def __init__(self, index_path: str = "data/faiss_index.bin", metadata_path: str = "data/faiss_metadata.json"):
        self.index_path = os.path.abspath(index_path)
        self.metadata_path = os.path.abspath(metadata_path)
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)

        self.index = None
        self.metadata: List[Dict] = []
        self._load_or_create()

    def _load_or_create(self):
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            try:
                self.index = faiss.read_index(self.index_path)
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
                logger.info(f"Загружен FAISS индекс: {self.index.ntotal} векторов")
            except Exception as e:
                logger.error(f"Ошибка загрузки: {e}. Создаем новый.")
                self._reset_state()
        else:
            self._reset_state()

    def _reset_state(self):
        self.index = None
        self.metadata = []

    def add(
        self,
        text: str,
        embedding: List[float],
        drawing_id: str,
        page: Optional[int] = None,
        kind: str = "ocr_chunk"
    ):
        # Обязательно приводим drawing_id к строке для консистентности
        drawing_id = str(drawing_id)

        if any(m['text'] == text and m['drawing_id'] == drawing_id for m in self.metadata):
            return

        vec = np.array(embedding, dtype=np.float32).reshape(1, -1)
        faiss.normalize_L2(vec)

        if self.index is None:
            dimension = vec.shape[1]
            self.index = faiss.IndexFlatIP(dimension)

        self.index.add(vec)
        self.metadata.append({
            "text": text,
            "drawing_id": drawing_id,
            "page": page,
            "kind": kind
        })
        self._save()

    def _save(self):
        if self.index is not None:
            faiss.write_index(self.index, self.index_path)
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)

    def delete_by_drawing_id(self, drawing_id: str) -> int:
        """
        Удаляет все векторы и метаданные, связанные с drawing_id.
        Пересобирает индекс FAISS из оставшихся векторов.
        Возвращает количество удаленных записей.
        """
        drawing_id = str(drawing_id)

        if self.index is None or self.index.ntotal == 0:
            return 0

        # Находим индексы элементов, которые нужно оставить, и те, что нужно удалить
        keep_indices = []
        new_metadata = []
        removed_count = 0

        for i, meta in enumerate(self.metadata):
            if meta.get('drawing_id') == drawing_id:
                removed_count += 1
            else:
                keep_indices.append(i)
                new_metadata.append(meta)

        # Если ничего не нашли для удаления, выходим
        if removed_count == 0:
            return 0

        # Если удалили вообще всё — сбрасываем базу в ноль
        if not keep_indices:
            self._reset_state()
            # Принудительно чистим файлы на диске, чтобы не оставалось старых данных
            if os.path.exists(self.index_path):
                os.remove(self.index_path)
            if os.path.exists(self.metadata_path):
                os.remove(self.metadata_path)
            logger.info(f"Все векторы для drawing_id {drawing_id} удалены. Индекс очищен.")
            return removed_count

        # Извлекаем оставшиеся векторы из старого индекса
        dimension = self.index.d
        remaining_vectors = []
        for idx in keep_indices:
            # Восстанавливаем вектор по его позиции i
            vec = self.index.reconstruct(idx)
            remaining_vectors.append(vec)

        # Пересобираем массив векторов
        remaining_vectors_np = np.array(remaining_vectors, dtype=np.float32)

        # Создаем новый чистый индекс той же размерности
        new_index = faiss.IndexFlatIP(dimension)
        new_index.add(remaining_vectors_np)

        # Обновляем состояние объекта
        self.index = new_index
        self.metadata = new_metadata

        # Сохраняем обновленный индекс на диск
        self._save()

        logger.info(f"Удалено {removed_count} векторов для drawing_id {drawing_id}. Индекс успешно пересобран. Осталось векторов: {self.index.ntotal}")
        return removed_count

    def search(self, query_embedding: List[float], drawing_id: Optional[str] = None, k: int = 5) -> List[Dict]:
        if self.index is None or self.index.ntotal == 0:
            return []

        vec = np.array(query_embedding, dtype=np.float32).reshape(1, -1)
        faiss.normalize_L2(vec)

        # Если задан drawing_id, нужно искать по всей базе, так как FAISS Flat не поддерживает нативную фильтрацию
        # Мы берем ntotal, чтобы гарантированно найти лучшие результаты для конкретного чертежа
        search_k = self.index.ntotal if drawing_id else k
        distances, indices = self.index.search(vec, search_k)

        results = []
        target_id = str(drawing_id) if drawing_id else None

        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1 or idx >= len(self.metadata):
                continue

            meta = self.metadata[idx]

            if target_id is None or meta['drawing_id'] == target_id:
                results.append({
                    "text": meta['text'],
                    "drawing_id": meta['drawing_id'],
                    "page": meta.get("page"),
                    "kind": meta.get("kind", "ocr_chunk"),
                    "score": float(dist)
                })

            if len(results) >= k:
                break

        return results
