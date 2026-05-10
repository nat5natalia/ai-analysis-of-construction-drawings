import os
import uuid
import httpx
import logging
from datetime import datetime, timezone
from typing import List, Optional
import asyncio
from vector_db import vector_db
from fastapi.responses import FileResponse
import mimetypes

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db import db_manager, save_drawing, get_drawing, delete_drawing
from celery_worker.worker import process_drawing as celery_process_task

from fastapi import WebSocket, WebSocketDisconnect
import json
import redis.asyncio as redis

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

import time
import uuid as uuid_lib

@app.middleware("http")
async def log_requests(request, call_next):
    request_id = str(uuid_lib.uuid4())
    # Сохраняем в контексте запроса (опционально)
    request.state.request_id = request_id
    start = time.time()
    logger.info(f"[{request_id}] --> {request.method} {request.url.path}")
    response = await call_next(request)
    elapsed = time.time() - start
    logger.info(f"[{request_id}] <-- {response.status_code} ({elapsed:.3f}s)")
    response.headers["X-Request-ID"] = request_id
    return response

class AskRequest(BaseModel):
    question: str


@app.on_event("startup")
async def startup_event():
    await db_manager.connect()
    # Создаём асинхронный Redis-клиент и сохраняем в app.state
    app.state.redis = redis.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=True
    )
    logger.info("Backend connected to MongoDB and Redis")


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


@app.get("/api/similar/{drawing_id}")
async def similar_drawings(drawing_id: str, limit: int = 5):
    """Поиск чертежей, похожих на заданный (по эмбеддингу описания)."""
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертёж не найден")
    embedding = meta.get("embedding")
    if not embedding:
        raise HTTPException(status_code=400, detail="Эмбеддинг отсутствует. Возможно, чертёж ещё не обработан.")
    # Поиск в FAISS (синхронная операция, выполняем в отдельном потоке)
    results = await asyncio.to_thread(vector_db.search, embedding, k=limit+1)
    # Исключаем сам запрашиваемый чертёж из результатов
    filtered = [(did, score) for did, score in results if did != drawing_id][:limit]
    return {
        "drawing_id": drawing_id,
        "similar": [{"id": did, "similarity": score} for did, score in filtered]
    }
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
        # Не валим весь запрос, просто помечаем ошибку очереди в БД
        await db_manager.collection.update_one(
            {"id": drawing_id},
            {"$set": {"status": "queued_failed", "error": str(e)}}
        )

    return {"id": drawing_id, "status": "processing"}

#вебсокет эндпоинт
@app.websocket("/ws/{drawing_id}")
async def websocket_endpoint(websocket: WebSocket, drawing_id: str):
    await websocket.accept()
    try:
        # Отправляем текущее состояние
        meta = await get_drawing(drawing_id)
        if meta:
            await websocket.send_json({
                "type": "status",
                "status": meta.get("status"),
                "messages": meta.get("messages", []),
                "error": meta.get("error")
            })

        # Подписываемся на обновления в Redis
        async with app.state.redis.pubsub() as pubsub:
            channel = f"drawing_updates:{drawing_id}"
            await pubsub.subscribe(channel)
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    await websocket.send_json(data)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for {drawing_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


@app.post("/api/ask/{drawing_id}")
async def ask_about_drawing(drawing_id: str, body: AskRequest):
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертеж не найден")

    try:
        # Ставим задачу в очередь
        task = celery_process_task.delay(drawing_id, body.question)

        # Сбрасываем статус в БД, чтобы фронтенд понимал, что идет новый процесс
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

@app.get("/api/drawings/{drawing_id}/file")
async def get_drawing_file(drawing_id: str):
    """Возвращает файл чертежа (PDF или изображение)."""
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертёж не найден")
    file_path = meta.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    # Определяем MIME-тип
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "application/octet-stream"
    return FileResponse(file_path, media_type=mime_type)

@app.get("/api/drawings/{drawing_id}/messages")
async def get_drawing_messages(drawing_id: str):
    """Возвращает всю историю диалога по чертежу."""
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертёж не найден")
    return {
        "drawing_id": drawing_id,
        "messages": meta.get("messages", [])
    }

@app.post("/api/drawings/{drawing_id}/messages")
async def send_message(drawing_id: str, body: AskRequest):
    """Отправить вопрос по чертежу (только если обработка завершена)."""
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертёж не найден")

    # Блокировка до завершения обработки
    if meta.get("status") != "completed":
        raise HTTPException(status_code=409, detail="Чертёж ещё обрабатывается, диалог невозможен")

    current_time = datetime.now(timezone.utc).isoformat()
    user_message = {
        "role": "user",
        "content": body.question,
        "ts": current_time
    }

    # Сохраняем вопрос в историю
    await db_manager.collection.update_one(
        {"id": drawing_id},
        {
            "$push": {"messages": user_message},
            "$set": {"status": "processing", "error": None}
        }
    )

    # Отправляем задачу в Celery
    try:
        task = celery_process_task.delay(drawing_id, body.question)
    except Exception as e:
        logger.error(f"Celery error: {e}")
        await db_manager.collection.update_one(
            {"id": drawing_id},
            {"$set": {"status": "failed", "error": str(e)}}
        )
        raise HTTPException(status_code=503, detail="Task queue unavailable")

    return {
        "drawing_id": drawing_id,
        "task_id": task.id,
        "status": "queued"
    }

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
    # 2. Удаляем из FAISS
    try:
        await asyncio.to_thread(vector_db.delete, drawing_id)
    except Exception as e:
        logger.warning(f"Could not delete from FAISS: {e}")
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