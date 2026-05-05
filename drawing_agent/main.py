import asyncio
import hydra
from omegaconf import DictConfig
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from app.agent import DrawingAgent
from rag.vectors import VectorDB

app = FastAPI(title="Drawing Agent API")

# Глобальные переменные для хранения инстансов
agent_instance = None


class AnalysisRequest(BaseModel):
    path: str
    question: str
    thread_id: str = "default_session"


@app.post("/process")
async def process_drawing(req: AnalysisRequest):
    """Эндпоинт для анализа чертежа"""
    if not agent_instance:
        raise HTTPException(status_code=503, detail="Агент еще инициализируется")

    result = await agent_instance.run(
        path=req.path,
        question=req.question,
        thread_id=req.thread_id
    )

    if result and result.get("success"):
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))


@hydra.main(config_path="config", config_name="config", version_base=None)
def main(cfg: DictConfig):
    global agent_instance

    # Инициализация логики агента
    vector_db = VectorDB(dimension=384)
    agent_instance = DrawingAgent(cfg, vector_db=vector_db)

    # Запуск сервера
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()