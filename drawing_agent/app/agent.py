import os
import time
import asyncio
import logging
import hashlib
import gc  # Добавили для принудительной очистки памяти
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
        self.lock = asyncio.Lock()  # Один замок на весь агент
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self.saver = None
        self.graph = None
        self.vector_db = vector_db
        self.drawing_knowledge = None

        self.cache = AgentCache(max_size=200, default_ttl=3600)
        self.stats = {"questions": 0, "total_time": 0, "errors": 0}

        init_clearml()

    async def _ensure_initialized(self):
        if self.saver is None:
            self._saver_manager = AsyncSqliteSaver.from_conn_string(self.db_path)
            self.saver = await self._saver_manager.__aenter__()
            self.graph = build_graph(self.cfg, checkpointer=self.saver)
            logger.info(f"LangGraph initialized with persistent checkpoint: {self.db_path}")

        if self.drawing_knowledge is None:
            if self.vector_db is None:
                from rag.vectors import VectorDB
                self.vector_db = VectorDB(
                    index_path=os.path.join(self.data_dir, "faiss_index.bin"),
                    metadata_path=os.path.join(self.data_dir, "faiss_metadata.json")
                )
            self.drawing_knowledge = DrawingKnowledgeManager(vector_db=self.vector_db)

    async def _run_heavy_operations(self, image_base64: str) -> Dict[str, Any]:
        """Последовательное выполнение инструментов для экономии памяти."""
        loop = asyncio.get_running_loop()
        set_current_drawing(image_base64)

        logger.info("Запуск ПОСЛЕДОВАТЕЛЬНОГО анализа чертежа...")

        yolo_res = await loop.run_in_executor(None, detect_yolo_objects.invoke, {})
        gc.collect()  # Очистка после YOLO

        geom_res = await loop.run_in_executor(None, extract_dimensions.invoke, {})
        holes_res = await loop.run_in_executor(None, detect_holes.invoke, {})
        tables_res = await loop.run_in_executor(None, detect_tables.invoke, {})
        gc.collect()  # Очистка перед самым тяжелым (OCR)

        ocr_res = await loop.run_in_executor(None, extract_text.invoke, {"image_base64": image_base64})
        gc.collect()

        return {
            "yolo": yolo_res,
            "geometry": geom_res,
            "holes": holes_res,
            "tables": tables_res,
            "full_ocr": ocr_res
        }

    async def pre_analyze(self, path: str, drawing_id: Optional[str] = None, page: int = 0) -> Dict:
        await self._ensure_initialized()

        # Используем lock, чтобы фоновый анализ не шел одновременно с вопросами
        async with self.lock:
            try:
                loop = asyncio.get_running_loop()

                # Если drawing_id не передан, генерируем его по хешу пути (для совместимости)
                if not drawing_id:
                    drawing_id = self.drawing_knowledge._get_drawing_hash(path, page)

                logger.info(f"Начало пре-анализа для: {path} (ID: {drawing_id})")

                # 1. Загрузка и первичное кэширование (картинка, OCR)
                # Передаем drawing_id в методы знаний, если они это поддерживают
                drawing_data = await loop.run_in_executor(
                    None, self.drawing_knowledge.load_drawing_and_cache, path, page
                )

                # 2. Инициализация RAG (индексация текста в векторную БД)
                self.drawing_knowledge.initialize_static_knowledge(path, page, drawing_data)

                # 3. Выполнение тяжелых операций (YOLO, OpenCV)
                heavy_results = await self._run_heavy_operations(drawing_data["image_base64"])

                # 4. Формирование и сохранение текстового отчета анализа
                heavy_analysis_text = (
                    f"--- РЕЗУЛЬТАТЫ ГЛУБОКОГО АНАЛИЗА ---\n"
                    f"ДЕТЕКЦИЯ ОБЪЕКТОВ (YOLO):\n{heavy_results['yolo']}\n\n"
                    f"ГЕОМЕТРИЯ (OpenCV):\n{heavy_results['geometry']}\n\n"
                    f"ОТВЕРСТИЯ:\n{heavy_results['holes']}\n\n"
                    f"ТАБЛИЦЫ:\n{heavy_results['tables']}\n\n"
                    f"ПОЛНЫЙ ТЕКСТ:\n{heavy_results['full_ocr']}"
                )

                await loop.run_in_executor(
                    None, self.drawing_knowledge.save_heavy_analysis, path, page, heavy_analysis_text
                )

                logger.info(f"Фоновый анализ завершен успешно для: {drawing_id}")
                return {"success": True, "error": None}

            except Exception as e:
                logger.error(f"Ошибка в pre_analyze для {path}: {e}", exc_info=True)
                return {"success": False, "error": str(e)}

    async def run(self, path: str, question: str, thread_id: Optional[str] = None, page: int = 0) -> Dict:
        await self._ensure_initialized()

        async with self.lock:
            start_time = time.time()
            if thread_id is None:
                thread_id = self._generate_stable_thread_id(path, page)

            config = {"configurable": {"thread_id": thread_id}}

            # Проверка оперативного кэша (LRU) на идентичный вопрос
            cached = self.cache.get(thread_id, path, question)
            if cached:
                log_cache_operation("get", f"{thread_id}:{question}", True)
                return cached

            try:
                loop = asyncio.get_running_loop()

                # Загружаем базовые данные чертежа (картинка, метаданные)
                drawing_data = await loop.run_in_executor(
                    None, self.drawing_knowledge.load_drawing_and_cache, path, page
                )

                heavy_analysis_text = await loop.run_in_executor(
                    None, self.drawing_knowledge.get_heavy_analysis, path, page
                )

                if not heavy_analysis_text:
                    logger.info(f"Кэш анализа не найден. Запуск нейросетей для {path}...")
                    heavy_results = await self._run_heavy_operations(drawing_data["image_base64"])

                    heavy_analysis_text = (
                        f"--- РЕЗУЛЬТАТЫ ГЛУБОКОГО АНАЛИЗА ---\n"
                        f"ДЕТЕКЦИЯ ОБЪЕКТОВ (YOLO):\n{heavy_results['yolo']}\n\n"
                        f"ГЕОМЕТРИЯ (OpenCV):\n{heavy_results['geometry']}\n\n"
                        f"ОТВЕРСТИЯ:\n{heavy_results['holes']}\n\n"
                        f"ТАБЛИЦЫ:\n{heavy_results['tables']}\n\n"
                        f"ПОЛНЫЙ ТЕКСТ:\n{heavy_results['full_ocr']}"
                    )

                    await loop.run_in_executor(
                        None, self.drawing_knowledge.save_heavy_analysis, path, page, heavy_analysis_text
                    )
                else:
                    logger.info(f"Используется готовый анализ из кэша (Fast Mode) для {path}")

                self.drawing_knowledge.initialize_static_knowledge(path, page, drawing_data)
                rag_context = self.drawing_knowledge.retrieve_context(path, page, question)

                initial_state = {
                    "messages": [HumanMessage(content=question)],
                    "current_drawing": drawing_data["image_base64"],
                    "drawing_width": drawing_data["width"],
                    "drawing_height": drawing_data["height"],
                    "ocr_text": drawing_data.get("ocr_text", ""),
                    "heavy_analysis": heavy_analysis_text,
                    "context": rag_context,
                    "analysis_complete": True  # Устанавливаем True, так как пре-анализ готов
                }

                result = await self.graph.ainvoke(initial_state, config={"configurable": {"thread_id": thread_id}})

                answer = self._extract_answer(result)
                final_output = result.get("final_output")

                if answer:
                    self.drawing_knowledge.add_interaction_to_index(path, page, question, answer)

                response_time = time.time() - start_time
                self.stats["questions"] += 1
                self.stats["total_time"] += response_time
                log_question_answer(question, answer, True, response_time)

                final_response = {
                    "success": True,
                    "answer": answer,
                    "data": final_output,
                    "error": None,
                    "execution_time": round(response_time, 2)
                }

                # Сохраняем в оперативный кэш
                self.cache.set(thread_id, path, question, final_response)
                return final_response

            except Exception as e:
                logger.error(f"Agent execution error: {e}", exc_info=True)
                self.stats["errors"] += 1
                return {"success": False, "answer": None, "error": str(e)}

    def _extract_answer(self, result: dict) -> str:
        if not result or "messages" not in result: return ""
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content: return msg.content
        return ""

    def _generate_stable_thread_id(self, path: str, page: int) -> str:
        identifier = f"{os.path.abspath(path)}_{page}"
        return hashlib.md5(identifier.encode()).hexdigest()

    async def close(self):
        if hasattr(self, '_saver_manager') and self._saver_manager:
            await self._saver_manager.__aexit__(None, None, None)
            logger.info("SQLite checkpointer connection closed.")
        close_clearml()