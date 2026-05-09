import os
import logging
import uvicorn
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from omegaconf import DictConfig
from contextlib import asynccontextmanager
from typing import Optional

from app.agent import DrawingAgent
from rag.vectors import VectorDB

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# Глобальные переменные для ресурсов
agent_instance: Optional[DrawingAgent] = None
cfg_global: Optional[DictConfig] = None
vector_db_global = None


# --- Lifespan: управление жизненным циклом приложения ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent_instance, vector_db_global, cfg_global
    logger.info("Initializing Drawing Agent resources...")
    try:
        # Инициализируем векторную БД
        vector_db_global = VectorDB()

        # Создаем экземпляр агента.
        agent_instance = DrawingAgent(cfg_global, vector_db=vector_db_global)

        logger.info("Drawing Agent instance created and ready for requests.")
    except Exception as e:
        logger.exception(f"Startup failed: {e}")

    yield

    if agent_instance:
        await agent_instance.close()
    logger.info("Drawing Agent shutdown complete.")


app = FastAPI(title="Drawing Agent API", lifespan=lifespan)


# --- Схемы данных ---
class AnalysisRequest(BaseModel):
    path: str
    question: str
    thread_id: Optional[str] = None
    page: int = 0


class SearchRequest(BaseModel):
    query: str
    limit: int = 10
    path: Optional[str] = None
    page: int = 0


class PreAnalyzeRequest(BaseModel):
    path: str
    page: int = 0


def validate_path(path: str) -> str:
    from urllib.parse import urlparse
    if "://" in path:
        parsed = urlparse(path)
        if parsed.scheme:
            raise HTTPException(status_code=400, detail="URI not allowed")

    data_dir = cfg_global.get("data_dir", "/app/dataset") if cfg_global else "/app/dataset"
    sanitized_path = os.path.abspath(os.path.realpath(path))
    allowed_root = os.path.abspath(os.path.realpath(data_dir))

    if not sanitized_path.startswith(allowed_root):
        logger.warning(f"Access denied: {sanitized_path} is outside {allowed_root}")
        raise HTTPException(status_code=400, detail="Path outside allowed dataset directory")

    if not os.path.exists(sanitized_path):
        raise HTTPException(status_code=404, detail="File not found")

    return sanitized_path


# --- Эндпоинты ---

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    """
    Проверка готовности агента.
    Теперь учитывает блокировку (занят ли агент вычислениями).
    """
    if agent_instance is None:
        return {"status": "initializing"}

    # Если замок захвачен — значит, идет тяжелый анализ
    if agent_instance.lock.locked():
        return {"status": "busy", "detail": "Agent is currently processing a drawing"}

    return {"status": "ready"}


@app.post("/pre-analyze")
async def pre_analyze_drawing(req: PreAnalyzeRequest):
    if agent_instance is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    path = validate_path(req.path)
    logger.info(f"Background pre-analysis started for: {path}")

    try:
        # Теперь метод внутри использует async with self.lock,
        # так что вызов безопасен и последователен
        result = await agent_instance.pre_analyze(path=path, page=req.page)

        if result.get("success"):
            return result

        raise HTTPException(status_code=500, detail=result.get("error"))
    except Exception as e:
        logger.exception(f"Pre-analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search")
async def search_in_vector_db(req: SearchRequest):
    if agent_instance is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    try:
        await agent_instance._ensure_initialized()

        drawing_id = None
        if req.path:
            valid_path = validate_path(req.path)
            drawing_id = agent_instance.drawing_knowledge._get_drawing_hash(valid_path, req.page)

        query_embedding = agent_instance.drawing_knowledge.embed_model.generate(req.query)

        results = agent_instance.vector_db.search(
            query_embedding=query_embedding,
            drawing_id=drawing_id,
            k=req.limit
        )

        return {"success": True, "results": results}
    except Exception as e:
        logger.exception(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/process")
async def process_drawing(req: AnalysisRequest):
    if agent_instance is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    path = validate_path(req.path)
    logger.info(f"Processing question for: {path} (Thread: {req.thread_id})")

    try:
        # Метод run тоже под замком внутри агента
        result = await agent_instance.run(
            path=path,
            question=req.question,
            thread_id=req.thread_id,
            page=req.page
        )

        if result.get("success"):
            return result

        raise HTTPException(status_code=500, detail=result.get("error"))

    except Exception as e:
        logger.exception(f"Process drawing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Точка входа ---
def run_server(cfg: DictConfig):
    global cfg_global
    cfg_global = cfg

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        timeout_keep_alive=600
    )


if __name__ == "__main__":
    import hydra


    @hydra.main(config_path="config", config_name="config", version_base=None)
    def main(cfg: DictConfig):
        run_server(cfg)


    main()