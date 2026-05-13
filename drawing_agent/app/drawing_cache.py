import json
import os
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import numpy as np

from rag.embeddings import EmbeddingGenerator
from .loader import load_drawing
from .preprocess import preprocess_image

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "all-MiniLM-L6-v2"


class DrawingKnowledgeManager:
    def __init__(self, vector_db, cache_dir: str = "cache/drawings"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.vector_db = vector_db

        self._embed_model = None
        self._indexed_drawings: set = set()

    @property
    def embed_model(self):
        if self._embed_model is None:
            logger.info(f"Инициализация EmbeddingGenerator...")
            self._embed_model = EmbeddingGenerator(model_name=EMBEDDING_MODEL)
        return self._embed_model

    def _get_drawing_hash(self, path: str, page: int) -> str:
        identifier = f"{os.path.abspath(path)}:{page}"
        return hashlib.md5(identifier.encode()).hexdigest()

    def _split_text(self, text: str, chunk_size: int = 600, overlap: int = 100) -> List[str]:
        if not text:
            return []
        chunks = []
        for i in range(0, len(text), chunk_size - overlap):
            chunks.append(text[i:i + chunk_size])
        return chunks

    def load_drawing_and_cache(self, path: str, page: int = 0) -> Dict[str, Any]:
        hash_id = self._get_drawing_hash(path, page)
        static_cache_path = self.cache_dir / f"{hash_id}_static.json"

        if static_cache_path.exists():
            try:
                with open(static_cache_path, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                return {
                    "image_base64": cached["image_base64"],
                    "ocr_text": cached.get("ocr_text", ""),
                    "width": cached.get("width", 1000),
                    "height": cached.get("height", 1000),
                    "hash_id": hash_id
                }
            except Exception as e:
                logger.warning(f"Ошибка кэша {hash_id}: {e}")

        images = load_drawing(path)
        if not images:
            raise ValueError(f"Файл не найден: {path}")

        target_page = page if page < len(images) else 0
        image = images[target_page]
        processed = preprocess_image(image)

        cache_data = {
            "image_base64": processed["image_base64"],
            "ocr_text": processed.get("ocr_text", ""),
            "width": image.width,
            "height": image.height,
            "timestamp": datetime.now().isoformat(),
            "hash": hash_id
        }

        with open(static_cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

        return cache_data

    def initialize_static_knowledge(self, path: str, page: int, static_data: Dict[str, Any]):
        hash_id = self._get_drawing_hash(path, page)

        if hash_id in self._indexed_drawings:
            return

        ocr_text = static_data.get("ocr_text", "")
        if not ocr_text or len(ocr_text.strip()) < 10:
            return

        chunks = self._split_text(ocr_text)

        for i, chunk in enumerate(chunks):
            content = f"[OCR Chunk {i}] {chunk}"
            embedding = self.embed_model.generate(content)
            self.vector_db.add(content, embedding, drawing_id=hash_id)

        self._indexed_drawings.add(hash_id)
        logger.info(f"Чертеж {hash_id} проиндексирован.")

    def add_interaction_to_index(self, path: str, page: int, question: str, answer: str):
        if not answer: return

        hash_id = self._get_drawing_hash(path, page)
        interaction_text = f"Previous Q: {question} | Previous A: {answer}"

        embedding = self.embed_model.generate(interaction_text)
        self.vector_db.add(interaction_text, embedding, drawing_id=hash_id)

        log_path = self.cache_dir / f"{hash_id}_sessions.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            log_entry = {"timestamp": datetime.now().isoformat(), "q": question, "a": answer}
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def retrieve_context(self, path: str, page: int, query: str, top_k: int = 5) -> str:
        """Поиск контекста ТОЛЬКО для текущего чертежа."""
        hash_id = self._get_drawing_hash(path, page)
        query_embedding = self.embed_model.generate(query)

        # Поиск в векторной БД
        search_results = self.vector_db.search(query_embedding, drawing_id=hash_id, k=top_k)

        if not search_results:
            return "No relevant context found in RAG."

        # Берем первый элемент из каждого результата (текст),
        # игнорируя остальные (score, metadata и т.д.), сколько бы их ни было.
        relevant_fragments = []
        for res in search_results:
            if isinstance(res, (list, tuple)) and len(res) > 0:
                relevant_fragments.append(str(res[0]))
            elif isinstance(res, str):
                relevant_fragments.append(res)

        return "\n\n---\n\n".join(relevant_fragments)
    def save_heavy_analysis(self, path: str, page: int, analysis_text: str):
        hash_id = self._get_drawing_hash(path, page)
        cache_path = self.cache_dir / f"{hash_id}_heavy.txt"

        # Убедимся, что папка существует (на случай очистки)
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(analysis_text)
        logger.info(f"Тяжелый анализ успешно кэширован: {hash_id}")

    def get_heavy_analysis(self, path: str, page: int) -> Optional[str]:
        hash_id = self._get_drawing_hash(path, page)
        cache_path = self.cache_dir / f"{hash_id}_heavy.txt"

        if cache_path.exists():
            logger.info(f"Тяжелый анализ загружен из кэша: {hash_id}")
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.read()
        return None