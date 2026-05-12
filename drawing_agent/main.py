import os
import logging
import uvicorn
import asyncio
import json
from datetime import datetime
from typing import List, Optional, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from omegaconf import DictConfig

from app.agent import DrawingAgent
from rag.vectors import VectorDB

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# Глобальные ресурсы приложения
agent_instance: Optional[DrawingAgent] = None
cfg_global: Optional[DictConfig] = None


# --- Схемы данных (Pydantic) ---

class AnalysisRequest(BaseModel):
    path: str = Field(..., description="Путь к файлу чертежа")
    question: str = Field(..., description="Текст вопроса к чертежу")
    thread_id: Optional[str] = None
    page: int = 0


class SearchRequest(BaseModel):
    query: str = Field(..., description="Поисковый запрос")
    limit: int = 10
    path: Optional[str] = None
    page: int = 0


class PreAnalyzeRequest(BaseModel):
    path: str
    page: int = 0


# --- Жизненный цикл приложения ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление инициализацией и завершением работы ресурсов."""
    global agent_instance, cfg_global
    logger.info("Initializing Drawing Agent resources...")

    try:
        # Инициализация векторной базы данных
        vector_db = VectorDB()
        # Создание экземпляра агента с внедрением зависимостей
        agent_instance = DrawingAgent(cfg_global, vector_db=vector_db)
        logger.info("Drawing Agent is ready.")
    except Exception as e:
        logger.exception(f"Critical startup error: {e}")

    yield

    if agent_instance:
        await agent_instance.close()
    logger.info("Shutdown complete.")


app = FastAPI(title="Drawing Agent API", lifespan=lifespan)


# --- Вспомогательные функции ---

def validate_path(path: Any) -> str:
    """Проверка пути на существование и безопасность (Path Traversal)."""
    if not isinstance(path, str) or not path:
        raise HTTPException(status_code=400, detail="Invalid path format: expected non-empty string")

    # Защита от URI схем
    if "://" in path:
        raise HTTPException(status_code=400, detail="URIs are not allowed as paths")

    data_dir = cfg_global.get("data_dir", "/app/dataset") if cfg_global else "/app/dataset"

    # Резолв абсолютного пути для проверки границ директории
    sanitized_path = os.path.abspath(os.path.realpath(path))
    allowed_root = os.path.abspath(os.path.realpath(data_dir))

    if not sanitized_path.startswith(allowed_root):
        logger.warning(f"Security alert: blocked access to {sanitized_path}")
        raise HTTPException(status_code=403, detail="Access denied: path outside allowed directory")

    if not os.path.exists(sanitized_path):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    return sanitized_path


def ensure_string(text: Any) -> str:
    """Гарантирует, что данные для LLM/tiktoken являются строкой."""
    if text is None:
        return ""
    if isinstance(text, str):
        return text
    try:
        return str(text)
    except Exception:
        return ""


# --- Обработчики API ---

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/ready")
async def readiness_check():
    """Проверка доступности агента и его текущей загруженности."""
    if agent_instance is None:
        return {"status": "initializing"}

    if agent_instance.lock.locked():
        return {"status": "busy", "detail": "Processing another drawing"}

    return {"status": "ready"}


@app.post("/pre-analyze")
async def pre_analyze(req: PreAnalyzeRequest):
    """Запуск фонового индексирования и первичного анализа чертежа."""
    if not agent_instance:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    valid_path = validate_path(req.path)
    try:
        result = await agent_instance.pre_analyze(path=valid_path, page=req.page)

        if result and result.get("success"):
            return result

        error_msg = ensure_string(result.get("error", "Unknown pre-analysis error"))
        raise HTTPException(status_code=500, detail=error_msg)

    except Exception as e:
        logger.exception("Pre-analysis failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search")
async def search(req: SearchRequest):
    """Поиск по векторной базе знаний чертежа."""
    if not agent_instance:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    try:
        await agent_instance._ensure_initialized()

        # Гарантируем строковый формат запроса для эмбеддинг-модели
        clean_query = ensure_string(req.query)
        if not clean_query:
            return {"success": True, "results": []}

        drawing_id = None
        if req.path:
            valid_path = validate_path(req.path)
            drawing_id = agent_instance.drawing_knowledge._get_drawing_hash(valid_path, req.page)

        # Генерация эмбеддинга и поиск
        query_embedding = agent_instance.drawing_knowledge.embed_model.generate(clean_query)
        results = agent_instance.vector_db.search(
            query_embedding=query_embedding,
            drawing_id=drawing_id,
            k=req.limit
        )

        return {"success": True, "results": results}
    except Exception as e:
        logger.exception("Search operation failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/process")
async def process(req: AnalysisRequest):
    """Обработка сложного вопроса к чертежу с использованием LLM-агента."""
    if not agent_instance:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    valid_path = validate_path(req.path)
    # Защита от пустых вопросов, которые ломают tiktoken
    clean_question = ensure_string(req.question)

    if not clean_question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        logger.info(f"Processing query for {os.path.basename(valid_path)}")

        result = await agent_instance.run(
            path=valid_path,
            question=clean_question,
            thread_id=req.thread_id,
            page=req.page
        )

        if result and result.get("success"):
            return result

        # Если в результате ошибка — приводим её к строке
        error_detail = ensure_string(result.get("error", "Internal agent error"))
        raise HTTPException(status_code=500, detail=error_detail)

    except Exception as e:
        logger.exception("Drawing processing error")
        # Тщательная очистка сообщения об ошибке для API
        raise HTTPException(status_code=500, detail=ensure_string(str(e)))


# --- Запуск ---

def run_server(cfg: DictConfig):
    global cfg_global
    cfg_global = cfg

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        timeout_keep_alive=600  # Увеличенный таймаут для тяжелых PDF
    )


if __name__ == "__main__":
    import hydra


    @hydra.main(config_path="config", config_name="config", version_base=None)
    def main(cfg: DictConfig):
        run_server(cfg)


    main()