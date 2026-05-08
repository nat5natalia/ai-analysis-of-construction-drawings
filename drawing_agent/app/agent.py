import os
import time
import asyncio
import logging
import hashlib
from typing import Dict, Optional, Any
from omegaconf import DictConfig
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .graph import build_graph
from .monitoring import init_clearml, close_clearml, log_question_answer, log_cache_operation
from .tools import (
    set_current_drawing,
    detect_yolo_objects,
    extract_dimensions,
    detect_holes,
    detect_tables,
    extract_text
)
from .drawing_cache import DrawingKnowledgeManager
from .cache import AgentCache

logger = logging.getLogger(__name__)


class DrawingAgent:
    def __init__(self, cfg: DictConfig, vector_db=None):
        self.cfg = cfg
        self.data_dir = cfg.get("data_dir", "./data")
        self.db_path = os.path.join(self.data_dir, "checkpoints.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        # Состояние инициализации
        self.saver = None
        self.graph = None
        self.vector_db = vector_db
        self.drawing_knowledge = None

        self.cache = AgentCache(max_size=200, default_ttl=3600)
        self.stats = {"questions": 0, "total_time": 0, "errors": 0}

        init_clearml()

    async def _ensure_initialized(self):
        """Гарантирует, что соединение с БД открыто и граф собран."""
        if self.saver is None:
            # 1. Создаем контекстный менеджер
            self._saver_manager = AsyncSqliteSaver.from_conn_string(self.db_path)

            # 2. Входим в него. Именно await __aenter__() возвращает
            # тот самый объект AsyncSqliteSaver, который ожидает LangGraph.
            self.saver = await self._saver_manager.__aenter__()

            # 3. Собираем граф, передавая чистый объект сейвера
            self.graph = build_graph(self.cfg, checkpointer=self.saver)
            logger.info(f"LangGraph initialized with persistent checkpoint: {self.db_path}")

        if self.drawing_knowledge is None:
            if self.vector_db is None:
                # Импортируем внутри, чтобы избежать циклических зависимостей
                from .vectors import VectorDB
                self.vector_db = VectorDB(
                    index_path=os.path.join(self.data_dir, "faiss_index.bin"),
                    metadata_path=os.path.join(self.data_dir, "faiss_metadata.json")
                )
            self.drawing_knowledge = DrawingKnowledgeManager(vector_db=self.vector_db)

    def _extract_answer(self, result: dict) -> str:
        if not result or "messages" not in result:
            return ""
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                return msg.content
        return ""

    def _generate_stable_thread_id(self, path: str, page: int) -> str:
        # Добавляем соль или уникальный маркер, если нужно сбросить историю
        identifier = f"{os.path.abspath(path)}_{page}"
        return hashlib.md5(identifier.encode()).hexdigest()

    async def _run_heavy_operations(self, image_base64: str) -> Dict[str, Any]:
        """Параллельное выполнение тяжелых инструментов."""
        loop = asyncio.get_running_loop()
        # ВАЖНО: set_current_drawing должен вызываться перед инвоками
        set_current_drawing(image_base64)

        logger.info("Запуск параллельного анализа чертежа (YOLO, OCR, OpenCV)...")
        tasks = {
            "yolo": loop.run_in_executor(None, detect_yolo_objects.invoke, {}),
            "geometry": loop.run_in_executor(None, extract_dimensions.invoke, {}),
            "holes": loop.run_in_executor(None, detect_holes.invoke, {}),
            "tables": loop.run_in_executor(None, detect_tables.invoke, {}),
            "full_ocr": loop.run_in_executor(None, extract_text.invoke, {"image_base64": image_base64})
        }

        results = await asyncio.gather(*tasks.values())
        return dict(zip(tasks.keys(), results))

    async def run(self, path: str, question: str, thread_id: Optional[str] = None, page: int = 0) -> Dict:
        """Основной цикл выполнения вопроса."""
        await self._ensure_initialized()
        start_time = time.time()

        if thread_id is None:
            thread_id = self._generate_stable_thread_id(path, page)

        config = {"configurable": {"thread_id": thread_id}}

        # 1. Проверка кэша ответов
        cached = self.cache.get(thread_id, path, question)
        if cached:
            log_cache_operation("get", f"{thread_id}:{question}", True)
            return cached

        try:
            # 2. Загрузка чертежа
            loop = asyncio.get_running_loop()
            drawing_data = await loop.run_in_executor(
                None, self.drawing_knowledge.load_drawing_and_cache, path, page
            )

            # 3. Выполнение анализа
            heavy_results = await self._run_heavy_operations(drawing_data["image_base64"])

            # 4. RAG
            self.drawing_knowledge.initialize_static_knowledge(path, page, drawing_data)
            rag_context = self.drawing_knowledge.retrieve_context(path, page, question)

            # 5. Формирование состояния
            initial_state = {
                "messages": [HumanMessage(content=question)],
                "current_drawing": drawing_data["image_base64"],
                "drawing_width": drawing_data["width"],
                "drawing_height": drawing_data["height"],
                "ocr_text": drawing_data.get("ocr_text", ""),
                "heavy_analysis": (
                    f"--- РЕЗУЛЬТАТЫ ГЛУБОКОГО АНАЛИЗА ---\n"
                    f"ДЕТЕКЦИЯ ОБЪЕКТОВ (YOLO):\n{heavy_results['yolo']}\n\n"
                    f"ГЕОМЕТРИЯ (OpenCV):\n{heavy_results['geometry']}\n\n"
                    f"ОТВЕРСТИЯ:\n{heavy_results['holes']}\n\n"
                    f"ТАБЛИЦЫ:\n{heavy_results['tables']}\n\n"
                    f"ПОЛНЫЙ ТЕКСТ:\n{heavy_results['full_ocr']}"
                ),
                "context": rag_context,
                "analysis_complete": False
            }

            # 6. Запуск графа
            result = await self.graph.ainvoke(initial_state, config=config)
            answer = self._extract_answer(result)

            if answer:
                self.drawing_knowledge.add_interaction_to_index(path, page, question, answer)

            response_time = time.time() - start_time
            self.stats["questions"] += 1
            self.stats["total_time"] += response_time
            log_question_answer(question, answer, True, response_time)

            final_response = {"success": True, "answer": answer, "error": None}
            self.cache.set(thread_id, path, question, final_response)
            return final_response

        except Exception as e:
            logger.error(f"Agent execution error: {e}", exc_info=True)
            self.stats["errors"] += 1
            return {"success": False, "answer": None, "error": str(e)}

    async def close(self):
        """Чистое закрытие ресурсов."""
        # Выходим из контекста сейвера, если он был инициализирован
        if hasattr(self, '_saver_manager') and self._saver_manager:
            await self._saver_manager.__aexit__(None, None, None)
            logger.info("SQLite checkpointer connection closed.")

        if hasattr(self.cache, 'flush_to_log'):
            self.cache.flush_to_log()

        close_clearml()