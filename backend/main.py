import os
import uuid
import httpx
import logging
from datetime import datetime, timezone
from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Импортируем менеджер и функции-хелперы из db.py
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

# Настройки
AGENT_URL = os.getenv("AGENT_URL", "http://drawing-agent:8000")
UPLOAD_DIR = os.getenv("DATASET_PATH", "uploads")

# Создаем папку для загрузок, если её нет
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
    """Получение списка всех чертежей через db_manager.collection"""
    collection = db_manager.collection
    cursor = collection.find({}, {"_id": 0})
    results = await cursor.skip(offset).limit(limit).to_list(length=limit)
    total = await collection.count_documents({})
    return {"total": total, "drawings": results}

@app.get("/api/drawings/{drawing_id}")
async def get_drawing_by_id(drawing_id: str):
    """Получение информации о конкретном чертеже"""
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертеж не найден")
    return meta

# --- 2. Загрузка и запуск обработки ---

@app.post("/api/upload")
async def upload_drawing(file: UploadFile = File(...)):
    """Загрузка файла и инициация обработки"""
    drawing_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1]
    save_path = os.path.join(UPLOAD_DIR, f"{drawing_id}{ext}")

    # Сохраняем файл на диск
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
        "description": None,
    }

    # Сохраняем в БД
    await save_drawing(drawing)

    # Запускаем Celery задачу (если импортирована)
    try:
        # celery_process_task.delay(drawing_id, "Сделай техническое описание чертежа.")
        pass
    except Exception as e:
        logger.error(f"Failed to dispatch Celery task: {e}")
        await db_manager.collection.update_one(
            {"id": drawing_id},
            {"$set": {"status": "queued_failed", "error": str(e)}}
        )

    return {"id": drawing_id, "status": "processing"}


@app.post("/api/ask/{drawing_id}")
async def ask_about_drawing(drawing_id: str, body: AskRequest):
    """Вопрос по конкретному чертежу через очередь"""
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертеж не найден")

    try:
        logger.info(f"Sending task to Celery for drawing {drawing_id}")

        task = celery_process_task.delay(drawing_id, body.question)

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
    """Удаление чертежа, файла и записи в БД"""
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертеж не найден")

    # Удаляем файл
    file_path = meta.get("file_path")
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            logger.warning(f"Could not delete file {file_path}: {e}")

    # Удаляем из БД
    success = await delete_drawing(drawing_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete record from database")

    return {"message": "Удалено успешно"}

# --- 4. Прокси-запросы к Агенту ---

@app.get("/api/search")
async def search_drawings(q: str, limit: int = 10):
    """Поиск через векторного агента"""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(f"{AGENT_URL}/search", json={"query": q, "limit": limit})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Agent search error: {e}")
            raise HTTPException(status_code=500, detail=f"Ошибка Агента: {str(e)}")


@app.get("/api/ask/status/{drawing_id}")
async def get_ask_status(drawing_id: str):
    """Проверка, появился ли ответ в БД"""
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертеж не найден")

    # Если ответ в БД уже появился (его туда запишет Celery по завершении)
    if meta.get("description"):
        return {
            "status": "completed",
            "answer": meta.get("description")
        }
    return {"status": "processing"}