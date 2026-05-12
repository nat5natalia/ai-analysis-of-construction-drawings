import os
import uuid
import httpx
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db import db_manager, save_drawing, get_drawing, delete_drawing
from celery_worker.worker import process_drawing as celery_process_task

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Анализ строительных чертежей",
    description="API с поддержкой Celery и векторного поиска",
    version="1.2.1"
)

AGENT_URL = os.getenv("AGENT_URL", "http://drawing_agent:8000")
UPLOAD_DIR = os.getenv("DATASET_PATH", "uploads")

os.makedirs(UPLOAD_DIR, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str


@app.on_event("startup")
async def startup_event():
    """Инициализируем асинхронное подключение к БД при старте"""
    await db_manager.connect()
    logger.info("Backend connected to MongoDB")


# --- 1. Поиск и метаданные ---

@app.get("/api/drawings")
async def get_all_drawings(limit: int = 20, offset: int = 0):
    collection = db_manager.collection
    cursor = collection.find({}, {"_id": 0})
    results = await cursor.skip(offset).limit(limit).to_list(length=limit)
    total = await collection.count_documents({})
    return {"total": total, "drawings": results}


@app.get("/api/drawings/{drawing_id}")
async def get_drawing_by_id(drawing_id: str):
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертеж не найден")
    return meta


# --- 2. Загрузка и запуск обработки ---

@app.post("/api/upload")
async def upload_drawing(file: UploadFile = File(...)):
    drawing_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1]
    save_path = os.path.join(UPLOAD_DIR, f"{drawing_id}{ext}")

    try:
        content = await file.read()
        with open(save_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        raise HTTPException(status_code=500, detail="Could not save file")

    drawing = {
        "id": drawing_id,
        "filename": file.filename,
        "status": "processing",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "file_path": save_path,
        "messages": [],
        "description": None,
    }

    await save_drawing(drawing)

    # Запускаем первичный анализ (техническое описание) через Celery
    try:
        celery_process_task.delay(drawing_id, "Сделай подробное техническое описание чертежа.")
    except Exception as e:
        logger.error(f"Failed to dispatch Celery task: {e}")
        await db_manager.collection.update_one(
            {"id": drawing_id},
            {"$set": {"status": "queued_failed", "error": str(e)}}
        )

    return {"id": drawing_id, "status": "processing"}


@app.post("/api/ask/{drawing_id}")
async def ask_about_drawing(drawing_id: str, body: AskRequest):
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертеж не найден")

    try:
        task = celery_process_task.delay(drawing_id, body.question)

        await db_manager.collection.update_one(
            {"id": drawing_id},
            {"$set": {"status": "processing"}}
        )

        return {
            "id": drawing_id,
            "task_id": task.id,
            "status": "queued"
        }
    except Exception as e:
        logger.error(f"Celery error: {e}")
        raise HTTPException(status_code=503, detail="Task queue unavailable")


# --- 3. Удаление ---

@app.delete("/api/drawings/{drawing_id}")
async def delete_drawing_by_id(drawing_id: str):
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертеж не найден")

    # 1. Удаляем физический файл
    file_path = meta.get("file_path")
    if file_path and os.path.exists(file_path):
        os.remove(file_path)

    # 2. Очищаем кэш в векторной базе (Агенте)
    async with httpx.AsyncClient() as client:
        try:
            # Отправляем запрос агенту, чтобы он удалил индексы этого файла
            await client.delete(f"{AGENT_URL}/cache/{drawing_id}")
        except Exception as e:
            logger.warning(f"Could not clear agent cache: {e}")

    # 3. Удаляем запись из MongoDB (вместе с историей messages)
    await delete_drawing(drawing_id)

    return {"message": "Всё удалено: файл, история и кэш"}


# --- 4. Прокси и Статус ---

@app.get("/api/search")
async def search_drawings(q: str, limit: int = 10, drawing_id: Optional[str] = None):
    """
    Поиск по векторной базе.
    Если передан drawing_id, ищем только в этом чертеже.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            # 1. Готовим тело запроса для Агента
            payload = {
                "query": q,
                "limit": limit
            }

            # 2. Если ищем в конкретном чертеже, нужно достать его путь из БД
            if drawing_id:
                meta = await get_drawing(drawing_id)
                if meta:
                    payload["path"] = meta.get("file_path")

            response = await client.post(f"{AGENT_URL}/search", json=payload)
            response.raise_for_status()

            return response.json()
        except Exception as e:
            logger.error(f"Agent search error: {e}")
            raise HTTPException(status_code=500, detail=f"Ошибка Агента: {str(e)}")

@app.get("/api/ask/status/{drawing_id}")
async def get_ask_status(drawing_id: str):
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертеж не найден")

    # Возвращаем текущее состояние из БД
    return {
        "status": meta.get("status"),
        "answer": meta.get("last_answer"),  # Celery пишет ответ сюда
        "error": meta.get("error")
    }