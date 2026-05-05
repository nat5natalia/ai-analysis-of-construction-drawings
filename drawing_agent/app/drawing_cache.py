import json
import hashlib
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
import numpy as np
from sentence_transformers import SentenceTransformer

# Используйте ту же модель, что в db.py
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

class DrawingKnowledgeManager:
    def __init__(self, vector_db, cache_dir: str = "cache/drawings"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.vector_db = vector_db   # <-- готовый экземпляр VectorDB
        self.embed_model = SentenceTransformer(EMBEDDING_MODEL)

    def _get_drawing_hash(self, path: str, page: int) -> str:
        return hashlib.md5(f"{path}:{page}".encode()).hexdigest()

    def _int_id(self, hash_id: str) -> int:
        h = hashlib.md5(hash_id.encode()).hexdigest()
        return np.int64(int(h[:16], 16) & 0x7FFFFFFFFFFFFFFF)

    def _get_static_cache_path(self, hash_id: str):
        return self.cache_dir / f"{hash_id}_static.json"

    def load_drawing_and_cache(self, path: str, page: int = 0) -> Dict[str, Any]:
        hash_id = self._get_drawing_hash(path, page)
        static_cache_path = self._get_static_cache_path(hash_id)

        if static_cache_path.exists():
            with open(static_cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            # Обратите внимание: load_drawing и preprocess_image импортируются локально,
            # чтобы избежать циклических зависимостей
            from app.data.loader import load_drawing
            images = load_drawing(path)
            image = images[page]
            return {"image_base64": cached["image_base64"],
                    "ocr_text": cached["ocr_text"],
                    "width": image.width, "height": image.height}

        from app.data.loader import load_drawing
        from app.data.preprocess import preprocess_image

        images = load_drawing(path)
        if page >= len(images):
            page = 0
        image = images[page]
        processed = preprocess_image(image)

        cache_data = {
            "image_base64": processed["image_base64"],
            "ocr_text": processed.get("ocr_text", ""),
            "timestamp": datetime.now().isoformat()
        }
        with open(static_cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

        return {"image_base64": cache_data["image_base64"],
                "ocr_text": cache_data["ocr_text"],
                "width": image.width, "height": image.height}

    def initialize_static_knowledge(self, path: str, page: int, static_data: Dict[str, Any]):
        hash_id = self._get_drawing_hash(path, page)
        num_id = self._int_id(hash_id)
        ocr_text = static_data.get("ocr_text", "")
        if not ocr_text:
            return
        fragment = f"Распознанный текст чертежа: {ocr_text}"
        vec = self.embed_model.encode(fragment, convert_to_numpy=True).astype('float32').reshape(1, -1)
        self.vector_db.add(vec, [num_id], [{"type": "static", "text": fragment, "drawing_hash": hash_id}])

    def add_interaction_to_index(self, path: str, page: int, question: str, answer: str):
        hash_id = self._get_drawing_hash(path, page)
        num_id = self._int_id(hash_id)
        combined = f"Вопрос: {question}\nОтвет: {answer}"
        vec = self.embed_model.encode(combined, convert_to_numpy=True).astype('float32').reshape(1, -1)
        self.vector_db.add(vec, [num_id], [{"type": "qa", "text": combined, "drawing_hash": hash_id}])

        log_path = self.cache_dir / f"{hash_id}_sessions.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            json.dump({"timestamp": datetime.now().isoformat(),
                       "question": question, "answer": answer}, f, ensure_ascii=False)
            f.write("\n")

    def retrieve_context(self, path: str, page: int, query: str, top_k: int = 4) -> str:
        hash_id = self._get_drawing_hash(path, page)
        query_vec = self.embed_model.encode(query, convert_to_numpy=True).astype('float32').reshape(1, -1)
        results = self.vector_db.search(query_vec, k=top_k)
        # Фильтруем по drawing_hash
        relevant = [r['metadata']['text'] for r in results
                    if r.get('metadata', {}).get('drawing_hash') == hash_id]
        return "\n\n".join(relevant)