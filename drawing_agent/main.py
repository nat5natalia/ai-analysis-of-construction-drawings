import asyncio
import logging
import uvicorn
import hydra
from omegaconf import DictConfig
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.agent import DrawingAgent
from rag.vectors import VectorDB

# Настройка логирования, чтобы видеть прогресс в консоли Docker
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Drawing Agent API")

# Глобальный инстанс агента
agent_instance = None


class AnalysisRequest(BaseModel):
    path: str
    question: str
    thread_id: str = "default_session"


@app.get("/health")
async def health_check():
    """Проверка готовности агента для Docker Healthcheck или Celery"""
    if agent_instance:
        return {"status": "ready"}
    return {"status": "initializing"}, 503


@app.post("/process")
async def process_drawing(req: AnalysisRequest):
    """Эндпоинт для анализа чертежа"""
    if not agent_instance:
        logger.error("Попытка вызова до завершения инициализации")
        raise HTTPException(status_code=503, detail="Агент еще инициализируется. Подождите 1-2 минуты.")

    logger.info(f"--- Новая задача: {req.thread_id} ---")
    logger.info(f"Файл: {req.path} | Вопрос: {req.question}")

    try:
        # ВАЖНО: убедись, что DrawingAgent.run — это async def
        result = await agent_instance.run(
            path=req.path,
            question=req.question,
            thread_id=req.thread_id
        )

        if result and result.get("success"):
            logger.info(f"Задача {req.thread_id} успешно выполнена")
            return result

        error_msg = result.get("error") if result else "Пустой ответ от логики агента"
        logger.error(f"Ошибка в логике агента: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

    except Exception as e:
        logger.exception(f"Критический сбой при обработке: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


@hydra.main(config_path="config", config_name="config", version_base=None)
def main(cfg: DictConfig):
    global agent_instance

    logger.info("Запуск процесса инициализации Drawing Agent...")

    try:
        # Инициализация VectorDB (384 — размерность для all-MiniLM-L6-v2)
        vector_db = VectorDB(dimension=384)

        # Инициализация самого агента (здесь загружаются YOLO, OCR и прочее)
        # ВАЖНО: Убедись, что в __init__ DrawingAgent нет бесконечных циклов
        agent_instance = DrawingAgent(cfg, vector_db=vector_db)

        logger.info("✅ Все модели загружены. Агент готов принимать запросы.")

        # Запуск Uvicorn
        # timeout_keep_alive=600 позволит держать соединение долго при тяжелой обработке
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info",
            timeout_keep_alive=600,
            access_log=True
        )
    except Exception as e:
        logger.error(f"Ошибка при старте сервера: {e}")
        raise e


if __name__ == "__main__":
    main()