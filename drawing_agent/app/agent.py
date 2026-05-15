import os
import time
import asyncio
import logging
import hashlib
import gc
from typing import Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor
from omegaconf import DictConfig
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
import psycopg
from psycopg.rows import dict_row

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
        self.lock = asyncio.Lock()
        os.makedirs(self.data_dir, exist_ok=True)

        self.saver = None
        self.graph = None
        self.vector_db = vector_db
        self.drawing_knowledge = None
        self._db_connection = None
        self._initialized = False
        
        self._executor = ThreadPoolExecutor(max_workers=4)

        self.cache = AgentCache(max_size=200, default_ttl=3600)
        self.stats = {"questions": 0, "total_time": 0, "errors": 0}

        init_clearml()

    async def _ensure_initialized(self):
        """Инициализация компонентов агента"""
        if self._initialized:
            return

        try:
            await self._init_database()
            await self._init_graph()
            await self._init_knowledge_base()
            
            self._initialized = True
            logger.info("Agent fully initialized")
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}", exc_info=True)
            raise

    async def _init_database(self):
        """Инициализация AsyncPostgresSaver"""
        postgres_dsn = os.getenv("DATABASE_URL")
        if not postgres_dsn:
            raise ValueError("DATABASE_URL environment variable is not set")
        
        self._db_connection = await psycopg.AsyncConnection.connect(
            postgres_dsn,
            autocommit=True,
            row_factory=dict_row,
            prepare_threshold=None
        )
        
        self.saver = AsyncPostgresSaver(self._db_connection)
        await self.saver.setup()
        
        logger.info("PostgreSQL initialized with AsyncPostgresSaver")

    async def _init_graph(self):
        """Инициализация графа LangGraph"""
        if self.saver is None:
            raise RuntimeError("Database saver not initialized")
        
        loop = asyncio.get_running_loop()
        self.graph = await loop.run_in_executor(
            self._executor,
            lambda: build_graph(self.cfg, checkpointer=self.saver)
        )
        logger.info("LangGraph initialized with PostgreSQL checkpoint")

    async def _init_knowledge_base(self):
        """Инициализация базы знаний"""
        # Всегда используем vector_db из celery_worker
        import sys
        sys.path.insert(0, '/celery_worker')
        from vector_db import vector_db
        self.vector_db = vector_db
    
        self.drawing_knowledge = DrawingKnowledgeManager(vector_db=self.vector_db)
        logger.info("Knowledge base initialized")

    async def _run_heavy_operations(self, image_base64: str) -> Dict[str, Any]:
        """Запуск тяжелых операций анализа изображения"""
        loop = asyncio.get_running_loop()
        set_current_drawing(image_base64)

        logger.info("Запуск последовательного анализа чертежа...")

        try:
            yolo_res = await loop.run_in_executor(None, detect_yolo_objects.invoke, {})
            gc.collect()

            geom_res = await loop.run_in_executor(None, extract_dimensions.invoke, {})
            holes_res = await loop.run_in_executor(None, detect_holes.invoke, {})
            tables_res = await loop.run_in_executor(None, detect_tables.invoke, {})
            gc.collect()

            ocr_res = await loop.run_in_executor(None, extract_text.invoke, {"image_base64": image_base64})
            gc.collect()

            return {
                "yolo": yolo_res,
                "geometry": geom_res,
                "holes": holes_res,
                "tables": tables_res,
                "full_ocr": ocr_res
            }
        except Exception as e:
            logger.error(f"Error in heavy operations: {e}", exc_info=True)
            return {
                "yolo": f"Error: {str(e)}",
                "geometry": f"Error: {str(e)}",
                "holes": f"Error: {str(e)}",
                "tables": f"Error: {str(e)}",
                "full_ocr": f"Error: {str(e)}"
            }

    async def _load_and_analyze_drawing(
        self, 
        path: str, 
        page: int, 
        force_reanalyze: bool = False,
        drawing_id: str = None
    ) -> Dict[str, Any]:
        """Загрузка и анализ чертежа с кэшированием"""
        loop = asyncio.get_running_loop()
        
        drawing_data = await loop.run_in_executor(
            None, self.drawing_knowledge.load_drawing_and_cache, path, page
        )
        
        if not drawing_data:
            raise ValueError(f"Failed to load drawing data for {path}")
        
        # Передаём drawing_id в initialize_static_knowledge
        self.drawing_knowledge.initialize_static_knowledge(path, page, drawing_data, drawing_id)
        
        heavy_analysis_text = None if force_reanalyze else await loop.run_in_executor(
            None, self.drawing_knowledge.get_heavy_analysis, path, page
        )
        
        if not heavy_analysis_text:
            logger.info(f"Запуск глубокого анализа для {path} (страница {page})...")
            
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
                None, self.drawing_knowledge.save_heavy_analysis, 
                path, page, heavy_analysis_text
            )
        else:
            logger.info(f"Используется кэшированный анализ для {path}")
        
        return {
            "drawing_data": drawing_data,
            "heavy_analysis_text": heavy_analysis_text
        }

    async def _save_drawing_embedding(
        self, 
        path: str, 
        drawing_id: str, 
        drawing_data: Dict[str, Any]
    ) -> bool:
        """Сохранение embedding для чертежа"""
        if not drawing_id or self.vector_db is None:
            return False
        
        try:
            if not hasattr(self.drawing_knowledge, 'embed_model'):
                logger.error("DrawingKnowledgeManager не имеет атрибута embed_model")
                return False
            
            text_for_embedding = f"Чертеж: {os.path.basename(path)}"
            if drawing_data.get("ocr_text"):
                text_for_embedding += f"\n{drawing_data['ocr_text']}"
            
            embedding = self.drawing_knowledge.embed_model.generate(text_for_embedding)
            
            import numpy as np
            embedding = embedding / np.linalg.norm(embedding)
            
            # Правильно: передаём только drawing_id и embedding
            self.vector_db.add(drawing_id, embedding.tolist())
            
            logger.info(f"✅ Embedding сохранен для drawing_id: {drawing_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения embedding: {e}", exc_info=True)
            return False

    async def pre_analyze(
        self, 
        path: str, 
        drawing_id: Optional[str] = None, 
        page: int = 0
    ) -> Dict[str, Any]:
        """Предварительный анализ чертежа"""
        logger.info(f"🔧 [pre_analyze] Начало: drawing_id={drawing_id}, path={path}, page={page}")
        
        await self._ensure_initialized()
        
        async with self.lock:
            try:
                # Передаём drawing_id в _load_and_analyze_drawing
                analysis = await self._load_and_analyze_drawing(path, page, drawing_id=drawing_id)
                
                if drawing_id:
                    await self._save_drawing_embedding(
                        path, drawing_id, analysis["drawing_data"]
                    )
                
                logger.info(f"✅ pre_analyze завершен успешно для: {path}")
                
                return {
                    "success": True,
                    "error": None,
                    "drawing_id": drawing_id
                }
                
            except Exception as e:
                logger.error(f"❌ Ошибка в pre_analyze: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": str(e)
                }

    async def run(
        self, 
        path: str, 
        question: str, 
        thread_id: Optional[str] = None, 
        page: int = 0,
        drawing_id: str = None
    ) -> Dict[str, Any]:
        """Выполнение запроса к агенту"""
        await self._ensure_initialized()
        
        async with self.lock:
            start_time = time.time()
            
            if thread_id is None:
                thread_id = self._generate_stable_thread_id(path, page)
            
            cached = self.cache.get(thread_id, path, question)
            if cached:
                log_cache_operation("get", f"{thread_id}:{question}", True)
                return cached
            
            try:
                analysis = await self._load_and_analyze_drawing(path, page, drawing_id=drawing_id)
                drawing_data = analysis["drawing_data"]
                heavy_analysis_text = analysis["heavy_analysis_text"]
                
                loop = asyncio.get_running_loop()
                rag_context = await loop.run_in_executor(
                    None, 
                    self.drawing_knowledge.retrieve_context,
                    path, page, question
                )
                
                initial_state = {
                    "messages": [HumanMessage(content=question)],
                    "current_drawing": drawing_data["image_base64"],
                    "drawing_width": drawing_data["width"],
                    "drawing_height": drawing_data["height"],
                    "ocr_text": drawing_data.get("ocr_text", ""),
                    "heavy_analysis": heavy_analysis_text,
                    "context": rag_context,
                    "analysis_complete": True
                }
                
                config = {"configurable": {"thread_id": thread_id}}
                result = await self.graph.ainvoke(initial_state, config)
                
                answer = self._extract_answer(result)
                final_output = result.get("final_output")
                
                if answer:
                    try:
                        self.drawing_knowledge.add_interaction_to_index(
                            path, page, question, answer, drawing_id
                        )
                    except Exception as e:
                        logger.warning(f"Не удалось добавить взаимодействие в индекс: {e}")
                
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
                
                self.cache.set(thread_id, path, question, final_response)
                
                return final_response
                
            except Exception as e:
                logger.error(f"❌ Ошибка выполнения: {e}", exc_info=True)
                self.stats["errors"] += 1
                return {
                    "success": False,
                    "answer": None,
                    "error": str(e)
                }

    def _extract_answer(self, result: dict) -> str:
        """Извлечение текстового ответа из результата графа"""
        if not result or "messages" not in result:
            return ""
        
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                return msg.content
        
        return ""

    def _generate_stable_thread_id(self, path: str, page: int) -> str:
        """Генерация стабильного идентификатора треда"""
        identifier = f"{os.path.abspath(path)}_{page}"
        return hashlib.md5(identifier.encode()).hexdigest()

    async def get_stats(self) -> Dict[str, Any]:
        """Получение статистики агента"""
        return {
            **self.stats,
            "avg_time": self.stats["total_time"] / max(self.stats["questions"], 1),
            "cache_size": len(self.cache.cache) if hasattr(self.cache, 'cache') else 0,
            "initialized": self._initialized
        }

    async def close(self):
        """Корректное закрытие всех ресурсов"""
        logger.info("Closing agent resources...")
        
        try:
            if self.saver and hasattr(self.saver, 'aclose'):
                await self.saver.aclose()
            
            if self._db_connection:
                await self._db_connection.close()
                logger.info("Database connection closed")
            
            if self._executor:
                self._executor.shutdown(wait=True)
            
            close_clearml()
            logger.info("Agent resources closed successfully")
            
        except Exception as e:
            logger.error(f"Error closing resources: {e}", exc_info=True)
        
        self._initialized = False