import os
import logging
import uvicorn
import asyncio
from datetime import datetime
from typing import List, Optional, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from omegaconf import DictConfig

from app.agent import DrawingAgent
from rag.vectors import VectorDB

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

agent_instance: Optional[DrawingAgent] = None
cfg_global: Optional[DictConfig] = None


class AnalysisRequest(BaseModel):
    path: str
    question: str
    thread_id: Optional[str] = None
    page: int = 0


class SearchRequest(BaseModel):
    query: str
    limit: int = 10
    path: Optional[str] = None
    drawing_id: Optional[str] = None  # UUID от бэкенда
    page: int = 0


class PreAnalyzeRequest(BaseModel):
    path: str
    drawing_id: Optional[str] = None  # Принимаем UUID при индексации
    page: int = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent_instance, cfg_global
    logger.info("Initializing Drawing Agent resources...")
    try:
        vector_db = VectorDB()
        agent_instance = DrawingAgent(cfg_global, vector_db=vector_db)

        # --- ПРОГРЕВ МОДЕЛИ ---
        # Инициализируем модель сразу при старте, чтобы не ждать 10 секунд на первом поиске
        await agent_instance._ensure_initialized()
        logger.info("Embedding model pre-loaded and Drawing Agent is ready.")
    except Exception as e:
        logger.exception(f"Critical startup error: {e}")
    yield
    if agent_instance:
        await agent_instance.close()


app = FastAPI(title="Drawing Agent API", lifespan=lifespan)


def validate_path(path: Any) -> str:
    if not isinstance(path, str) or not path or "://" in path:
        raise HTTPException(status_code=400, detail="Invalid path")
    data_dir = cfg_global.get("data_dir", "/app/dataset") if cfg_global else "/app/dataset"
    sanitized_path = os.path.abspath(os.path.realpath(path))
    allowed_root = os.path.abspath(os.path.realpath(data_dir))
    if not sanitized_path.startswith(allowed_root):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.exists(sanitized_path):
        raise HTTPException(status_code=404, detail="File not found")
    return sanitized_path


def ensure_string(text: Any) -> str:
    return str(text) if text is not None else ""


@app.post("/search")
async def search(req: SearchRequest):
    if not agent_instance:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    try:
        clean_query = ensure_string(req.query)

        # Важная правка логики определения ID
        drawing_id = req.drawing_id

        # Если бэкенд не прислал UUID, но прислал путь — генерируем хеш
        # ВАЖНО: этот метод должен быть идентичен тому, что использовался при индексации!
        if not drawing_id and req.path:
            valid_path = validate_path(req.path)
            drawing_id = agent_instance.drawing_knowledge._get_drawing_hash(valid_path, req.page)

        # Глобальный поиск, если drawing_id все еще None
        logger.info(f"Searching for: '{clean_query}' | Scope: {drawing_id or 'Global'}")

        query_embedding = agent_instance.drawing_knowledge.embed_model.generate(clean_query)

        results = agent_instance.vector_db.search(
            query_embedding=query_embedding,
            drawing_id=drawing_id,
            k=req.limit
        )

        return {"success": True, "results": results}
    except Exception as e:
        logger.exception("Search failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pre-analyze")
async def pre_analyze(req: PreAnalyzeRequest):
    if not agent_instance:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    valid_path = validate_path(req.path)

    # Если бэкенд прислал UUID, используем его. Если нет — используем внутренний хеш.
    # Это гарантирует, что поиск и индексация всегда используют одну и ту же "ключевую" строку.
    idx_id = req.drawing_id or agent_instance.drawing_knowledge._get_drawing_hash(valid_path, req.page)

    try:
        logger.info(f"Indexing drawing: {valid_path} with ID: {idx_id}")
        result = await agent_instance.pre_analyze(
            path=valid_path,
            drawing_id=idx_id,
            page=req.page
        )
        return result
    except Exception as e:
        logger.exception("Pre-analysis failed")
        raise HTTPException(status_code=500, detail=str(e))


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