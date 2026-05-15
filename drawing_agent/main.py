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
try:
    from celery_worker.vector_db import vector_db
    from celery_worker.ds import compute_embedding
except ModuleNotFoundError:
    import sys
    import os
    # Добавляем путь к celery_worker (который будет смонтирован через volume)
    sys.path.insert(0, '/celery_worker')
    from vector_db import vector_db
    from ds import compute_embedding

from pymongo import MongoClient
import numpy as np
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
    drawing_id: Optional[str] = None
    page: int = 0


class PreAnalyzeRequest(BaseModel):
    path: str
    drawing_id: Optional[str] = None 
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
    logger.info(f"📥 [AGENT] Received pre-analyze: drawing_id={req.drawing_id}, path={req.path}, page={req.page}")
    if agent_instance is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    path = validate_path(req.path)
    drawing_id = req.drawing_id
    logger.info(f"Background pre-analysis started for: {path}")

    try:
        result = await agent_instance.pre_analyze(path=path, drawing_id=drawing_id, page=req.page)

        if result.get("success"):
            return result

        raise HTTPException(status_code=500, detail=result.get("error"))
    except Exception as e:
        logger.exception(f"Pre-analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    

@app.get("/api/search")
async def search_drawings(q: str, limit: int = 10, offset: int = 0):
    """
    Поиск по локальной векторной базе FAISS (прямой доступ, без агента).
    """
    
    logger.info(f"🔍 [SEARCH] Local FAISS search: query='{q}', limit={limit}")
    q = q.strip()
    if not q:
        return {"success": True, "results": []}
    
    try:
        global vector_db
        global compute_embedding
        # Вычисляем эмбеддинг запроса
        embedding = compute_embedding(q)
        emb_np = np.array(embedding)
        emb_np = emb_np / np.linalg.norm(emb_np)
        
        # Ищем в FAISS
        results = vector_db.search(emb_np.tolist(), k=limit)
        
        # Получаем данные из MongoDB
        client = MongoClient("mongodb://drawing_mongo:27017/")
        db = client['drawings_db']
        
        output = []
        for doc_id, score in results:
            doc = db.drawings.find_one({"id": doc_id})
            if doc:
                output.append({
                    "drawing_id": doc_id,
                    "score": score,
                    "description": doc.get("description", "")[:300],
                    "filename": doc.get("filename", "")
                })
        
        client.close()
        
        logger.info(f" [SEARCH] Found {len(output)} results")
        return {"success": True, "results": output}
        
    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
    
@app.post("/search")  # ← добавляем то, чего не хватает
async def search_compat(request: dict):
    """
    Совместимость с POST /search (для старого клиента)
    """
    query = request.get("query") or request.get("q")
    limit = request.get("limit", 10)
    
    if not query:
        raise HTTPException(status_code=400, detail="Missing 'query' parameter")
    
    logger.info(f"POST /search compatibility endpoint: query='{query}', limit={limit}")
    
    # Вызываем существующий GET /api/search
    return await search_drawings(q=query, limit=limit)
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