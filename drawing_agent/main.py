import logging
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from omegaconf import DictConfig

from app.agent import DrawingAgent
from rag.vectors import VectorDB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Drawing Agent API")

agent_instance: DrawingAgent | None = None
cfg_global: DictConfig | None = None
vector_db_global = None


class AnalysisRequest(BaseModel):
    path: str
    question: str
    thread_id: str = "default_session"


# ---------------------------
# HEALTH (быстрый, всегда OK)
# ---------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    if agent_instance is None:
        return {"status": "initializing"}
    return {"status": "ready"}


# ---------------------------
# STARTUP (ключевой фикс)
# ---------------------------
@app.on_event("startup")
async def startup():
    global agent_instance, vector_db_global, cfg_global

    logger.info("Initializing Drawing Agent...")

    try:
        vector_db_global = VectorDB()
        agent_instance = DrawingAgent(cfg_global, vector_db=vector_db_global)

        logger.info("Drawing Agent ready")
    except Exception as e:
        logger.exception(f"Startup failed: {e}")
        raise


# ---------------------------
# PROCESS
# ---------------------------
@app.post("/process")
async def process_drawing(req: AnalysisRequest):
    if agent_instance is None:
        raise HTTPException(status_code=503, detail="Agent is still initializing")

    import os
    from urllib.parse import urlparse

    if "://" in req.path:
        parsed = urlparse(req.path)
        if parsed.scheme:
            raise HTTPException(status_code=400, detail="URI not allowed")

    sanitized_path = os.path.realpath(req.path)

    allowed_root = os.path.realpath("/app/dataset")
    if not sanitized_path.startswith(allowed_root):
        raise HTTPException(status_code=400, detail="Path outside dataset")

    if not os.path.exists(sanitized_path):
        raise HTTPException(status_code=400, detail="File not found")

    logger.info(f"Processing: {sanitized_path}")

    try:
        result = await agent_instance.run(
            path=sanitized_path,
            question=req.question,
            thread_id=req.thread_id
        )

        if result.get("success"):
            return result

        raise HTTPException(status_code=500, detail=result.get("error"))

    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------
# ENTRYPOINT
# ---------------------------
def run_server(cfg: DictConfig):
    """
    Вызывается из Hydra или обычного python entrypoint
    """
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
    # fallback без hydra
    import hydra

    @hydra.main(config_path="config", config_name="config", version_base=None)
    def main(cfg: DictConfig):
        run_server(cfg)

    main()