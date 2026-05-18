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

    def initialize_static_knowledge(self, path: str, page: int, static_data: Dict[str, Any], drawing_id: str = None):
        """Индексация OCR текста чертежа"""
        hash_id = self._get_drawing_hash(path, page)
        
        # Используем drawing_id из MongoDB, если передан
        actual_id = drawing_id if drawing_id else hash_id

        if hash_id in self._indexed_drawings:
            return

        ocr_text = static_data.get("ocr_text", "")
        if not ocr_text or len(ocr_text.strip()) < 10:
            return

        chunks = self._split_text(ocr_text)

        for i, chunk in enumerate(chunks):
            content = f"[OCR Chunk {i}] {chunk}"
            embedding = self.embed_model.generate(content)
            # Передаем сам текст content, чтобы он сохранился в метаданных.
            self.vector_db.add(
                text=content,
                embedding=embedding,
                drawing_id=actual_id,
                page=page,
                kind="ocr_chunk"
            )

        self._indexed_drawings.add(hash_id)
        logger.info(f"Чертеж {actual_id} проиндексирован.")

    def add_interaction_to_index(self, path: str, page: int, question: str, answer: str, drawing_id: str = None):
        """Индексация взаимодействия вопрос-ответ"""
        if not answer:
            return

        hash_id = self._get_drawing_hash(path, page)
        actual_id = drawing_id if drawing_id else hash_id
        
        text_for_embedding = f"Previous Q: {question} | Previous A: {answer}"
        
        embedding = self.embed_model.generate(text_for_embedding)
        # Сохраняем историю вопросов-ответов с привязкой к чертежу.
        self.vector_db.add(
            text=text_for_embedding,
            embedding=embedding,
            drawing_id=actual_id,
            kind="qa_interaction"
        )

        # Логируем в файл
        log_path = self.cache_dir / f"{hash_id}_sessions.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            log_entry = {"timestamp": datetime.now().isoformat(), "q": question, "a": answer}
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def retrieve_context(self, path: str, page: int, query: str, top_k: int = 5) -> str:
        """Поиск контекста в векторной БД"""
        query_embedding = self.embed_model.generate(query)

        # Поиск в векторной БД
        search_results = self.vector_db.search(query_embedding, k=top_k)

        if not search_results:
            return "No relevant context found in RAG."

        # Собираем контекст из реальных текстовых фрагментов, найденных в БД.
        context_chunks = [res["text"] for res in search_results if "text" in res]
        if not context_chunks:
            return "No relevant context found for this drawing."

        return "\n---\n".join(context_chunks)

    def save_heavy_analysis(self, path: str, page: int, analysis_text: str):
        hash_id = self._get_drawing_hash(path, page)
        cache_path = self.cache_dir / f"{hash_id}_heavy.txt"

        cache_path.parent.mkdir(parents=True, exist_ok=True)

        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(analysis_text)
        logger.info(f"Тяжелый анализ успешно кэширован: {hash_id}")

    def get_heavy_analysis(self, path: str, page: int) -> Optional[str]:
        hash_id = self._get_drawing_hash(path, page)
        cache_path = self.cache_dir / f"{hash_id}_heavy.txt"
        
        if cache_path.exists():
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.read()
        return None
