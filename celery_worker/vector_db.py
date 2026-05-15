
import os
import json
import numpy as np
import faiss
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)

class VectorDB:
    def __init__(self):
        # Используем путь из переменной окружения или стандартный
        base_path = '/app/data'
        os.makedirs(base_path, exist_ok=True)
        
        self.index_path = os.path.join(base_path, 'faiss_index.bin')
        self.metadata_path = os.path.join(base_path, 'faiss_metadata.json')
        self.index = None
        self.metadata = []
        self._load_or_create()
        logger.info(f'VectorDB initialized: {self.index_path}')

    def _load_or_create(self):
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            try:
                self.index = faiss.read_index(self.index_path)
                with open(self.metadata_path, 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)
                logger.info(f'✅ Loaded {self.index.ntotal} vectors, {len(self.metadata)} IDs')
            except Exception as e:
                logger.error(f'Load error: {e}, creating new')
                self._create_new()
        else:
            self._create_new()

    def _create_new(self):
        self.index = faiss.IndexFlatIP(384)
        self.metadata = []
        self._save()
        logger.info('✅ Created new FAISS index')

    def _save(self):
        try:
            faiss.write_index(self.index, self.index_path)
            with open(self.metadata_path, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False)
            logger.info(f'💾 Saved: {self.index.ntotal} vectors')
        except Exception as e:
            logger.error(f'Save error: {e}')

    def add(self, drawing_id: str, embedding: List[float]):
        vec = np.array(embedding, dtype=np.float32).reshape(1, -1)
        faiss.normalize_L2(vec)
        
        before = self.index.ntotal
        self.index.add(vec)
        self.metadata.append(drawing_id)
        self._save()
        
        logger.info(f'✅ Added {drawing_id}: {before} -> {self.index.ntotal}')
        return True

    def search(self, query_embedding: List[float], k: int = 10) -> List[Tuple[str, float]]:
        if self.index.ntotal == 0:
            return []
        
        vec = np.array(query_embedding, dtype=np.float32).reshape(1, -1)
        faiss.normalize_L2(vec)
        distances, indices = self.index.search(vec, min(k, self.index.ntotal))
        
        results = []
        for idx, dist in zip(indices[0], distances[0]):
            if idx != -1 and idx < len(self.metadata):
                results.append((self.metadata[idx], float(dist)))
        return results

    def delete(self, drawing_id: str):
        if drawing_id not in self.metadata:
            return
        
        indices_to_keep = [i for i, did in enumerate(self.metadata) if did != drawing_id]
        
        if not indices_to_keep:
            self.index.reset()
            self.metadata = []
        else:
            old_vectors = self.index.reconstruct_n(0, self.index.ntotal)
            new_vectors = np.array([old_vectors[i] for i in indices_to_keep], dtype=np.float32)
            new_metadata = [self.metadata[i] for i in indices_to_keep]
            self.index = faiss.IndexFlatIP(self.index.d)
            if len(new_vectors) > 0:
                faiss.normalize_L2(new_vectors)
                self.index.add(new_vectors)
            self.metadata = new_metadata
        self._save()

# Глобальный экземпляр
vector_db = VectorDB()