import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import numpy as np
from sentence_transformers import SentenceTransformer
from .loader import load_drawing
from .preprocess import preprocess_image

EMBEDDING_MODEL = "all-MiniLM-L6-v2"


class DrawingKnowledgeManager:
    def __init__(self, vector_db, cache_dir: str = "cache/drawings"):
        # Путь теперь будет считаться относительно корня drawing_agent
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.vector_db = vector_db  # Экземпляр VectorDB из rag.vectors
        self.embed_model = SentenceTransformer(EMBEDDING_MODEL)

    def _get_drawing_hash(self, path: str, page: int) -> str:
        """Создает уникальный MD5 хеш для пары файл:страница."""
        return hashlib.md5(f"{path}:{page}".encode()).hexdigest()

    def _get_static_cache_path(self, hash_id: str) -> Path:
        return self.cache_dir / f"{hash_id}_static.json"

    def load_drawing_and_cache(self, path: str, page: int = 0) -> Dict[str, Any]:
        """Загружает чертеж через app.data.loader и кэширует результат."""
        hash_id = self._get_drawing_hash(path, page)
        static_cache_path = self._get_static_cache_path(hash_id)



        if static_cache_path.exists():
            try:
                with open(static_cache_path, "r", encoding="utf-8") as f:
                    cached = json.load(f)

                images = load_drawing(path)
                if page >= len(images): page = 0
                image = images[page]

                return {
                    "image_base64": cached["image_base64"],
                    "ocr_text": cached.get("ocr_text", ""),
                    "width": image.width,
                    "height": image.height
                }
            except Exception:
                # Если кэш поврежден, идем дальше к пересозданию
                pass

        # Обработка нового файла
        images = load_drawing(path)
        if page >= len(images):
            page = 0
        image = images[page]

        processed = preprocess_image(image)

        cache_data = {
            "image_base64": processed["image_base64"],
            "ocr_text": processed.get("ocr_text", ""),
            "timestamp": datetime.now().isoformat(),
            "hash": hash_id
        }

        with open(static_cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

        return {
            "image_base64": cache_data["image_base64"],
            "ocr_text": cache_data["ocr_text"],
            "width": image.width,
            "height": image.height
        }

    def initialize_static_knowledge(self, path: str, page: int, static_data: Dict[str, Any]):
        """Сохраняет статические данные (OCR) в VectorDB."""
        hash_id = self._get_drawing_hash(path, page)
        ocr_text = static_data.get("ocr_text", "")

        if not ocr_text:
            return

        # Добавляем префикс ID для последующей фильтрации в RAG
        content = f"Drawing_ID:{hash_id} | OCR_TEXT: {ocr_text}"
        embedding = self.embed_model.encode(content).tolist()

        # Вызов вашего метода add(text, embedding) из rag/vectors.py
        self.vector_db.add(content, embedding)

    def add_interaction_to_index(self, path: str, page: int, question: str, answer: str):
        """Сохраняет историю диалога в векторную базу и лог."""
        hash_id = self._get_drawing_hash(path, page)
        interaction_text = f"Drawing_ID:{hash_id} | Q: {question} | A: {answer}"

        embedding = self.embed_model.encode(interaction_text).tolist()
        self.vector_db.add(interaction_text, embedding)

        # Логирование сессии в JSONL
        log_path = self.cache_dir / f"{hash_id}_sessions.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "question": question,
                "answer": answer
            }
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def retrieve_context(self, path: str, page: int, query: str, top_k: int = 5) -> str:
        """Поиск контекста, специфичного для данного хеша чертежа."""
        hash_id = self._get_drawing_hash(path, page)
        query_embedding = self.embed_model.encode(query).tolist()

        # Поиск в FAISS (возвращает List[Tuple[text, score]])
        search_results = self.vector_db.search(query_embedding, k=top_k)

        relevant_fragments = []
        target_prefix = f"Drawing_ID:{hash_id}"

        for text, score in search_results:
            if target_prefix in text:
                # Убираем технический ID перед возвратом в LLM
                clean_text = text.replace(f"{target_prefix} | ", "")
                relevant_fragments.append(clean_text)

        return "\n\n".join(relevant_fragments)