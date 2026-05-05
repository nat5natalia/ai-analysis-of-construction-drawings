# app/agent.py
import os
import time
import asyncio
from typing import Dict, Optional
from omegaconf import DictConfig
from langchain_core.messages import HumanMessage, AIMessage
from .graph import build_graph
from .monitoring import init_clearml, close_clearml, log_question_answer, log_cache_operation
from .tools import set_current_drawing
from .drawing_cache import DrawingKnowledgeManager
from .cache import AgentCache
import logging
logger = logging.getLogger(__name__)


class DrawingAgent:
    def __init__(self, cfg: DictConfig, vector_db=None):
        self.cfg = cfg
        if vector_db is None:
            from vector_db import VectorDB
            vector_db = VectorDB(dimension=384)

        self.drawing_knowledge = DrawingKnowledgeManager(vector_db=vector_db)
        # ВАЖНО: build_graph должен возвращать скомпилированный асинхронный граф
        self.graph = build_graph(cfg)
        init_clearml()
        self.stats = {"questions": 0, "total_time": 0, "errors": 0}
        self.cache = AgentCache()

    def _extract_answer(self, result: dict) -> str:
        if not result or "messages" not in result:
            return ""
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                return msg.content
        return ""

    async def run(self, path: str, question: str, wait_time: Optional[int] = None,
                  max_retries: Optional[int] = None, thread_id: Optional[str] = None,
                  page: int = 0) -> Dict:
        start_time = time.time()
        if thread_id is None:
            thread_id = "default"

        config = {"configurable": {"thread_id": thread_id}}
        cache_key = f"{thread_id}:{path}:{page}:{question}"

        cached = self.cache.get(cache_key)
        if cached:
            log_cache_operation("get", cache_key, True)
            return cached

        log_cache_operation("get", cache_key, False)

        try:
            # Загрузка данных чертежа (синхронная или обернутая в thread)
            drawing_data = self.drawing_knowledge.load_drawing_and_cache(path, page)
            image_base64 = drawing_data["image_base64"]
            ocr_text = drawing_data.get("ocr_text", "")
            width = drawing_data["width"]
            height = drawing_data["height"]

            set_current_drawing(image_base64)

            self.drawing_knowledge.initialize_static_knowledge(path, page, drawing_data)
            rag_context = self.drawing_knowledge.retrieve_context(path, page, question)

            initial_state = {
                "messages": [HumanMessage(content=question)],
                "current_drawing": image_base64,
                "drawing_width": width,
                "drawing_height": height,
                "page": page,
                "ocr_text": ocr_text,
                "context": rag_context,
                "analysis_complete": False  # Инициализируем флаг
            }

            # Вызов асинхронного графа
            result = await self.graph.ainvoke(initial_state, config=config)
            answer = self._extract_answer(result)

            if answer:
                self.drawing_knowledge.add_interaction_to_index(path, page, question, answer)

            response_time = time.time() - start_time
            self.stats["questions"] += 1
            self.stats["total_time"] += response_time
            log_question_answer(question, answer, True, response_time)

            final = {"success": True, "answer": answer, "error": None}
            self.cache.set(cache_key, final)
            log_cache_operation("set", cache_key, True)
            return final

        except Exception as e:
            logger.error(f"Agent run failed: {e}", exc_info=True)
            self.stats["errors"] += 1
            return {"success": False, "answer": None, "error": str(e)}

    def close(self):
        self.cache.flush_to_log()
        close_clearml()