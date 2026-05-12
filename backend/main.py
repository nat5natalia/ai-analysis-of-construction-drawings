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
from pdf import file_to_images_base64

import asyncio
import redis.asyncio as redis
import json
from fastapi import WebSocket, WebSocketDisconnect
from connection_manager import manager

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Анализ строительных чертежей",
    description="API с поддержкой Celery и отдачей превью в формате объекта image",
    version="1.5.0"
)

AGENT_URL = os.getenv("AGENT_URL", "http://drawing_agent:8000")
UPLOAD_DIR = os.getenv("DATASET_PATH", "uploads")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

os.makedirs(UPLOAD_DIR, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str


# --- Фоновая задача для уведомлений ---

async def redis_listener():
    """
    Слушает канал уведомлений в Redis. Когда Celery публикует сообщение,
    этот цикл перехватывает его и отправляет в соответствующий WebSocket.
    """
    r = redis.from_url(REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe("drawing_updates")

    logger.info("Redis Listener started: listening for drawing_updates")

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_init=True)
            if message:
                data = json.loads(message["data"])
                d_id = data.get("drawing_id")
                await manager.send_to_drawing(data, d_id)
            await asyncio.sleep(0.1)  # Микропауза для разгрузки процессора
    except Exception as e:
        logger.error(f"Redis Listener Error: {e}")


@app.on_event("startup")
async def startup_event():
    await db_manager.connect()
    # Запускаем "слушателя" Redis в фоне, чтобы он не блокировал API
    asyncio.create_task(redis_listener())
    logger.info("Backend connected to MongoDB and Redis Listener started")


# --- Вспомогательная функция для соответствия интерфейсу фронтенда ---

def inject_image_data(drawing_meta: dict, all_pages: bool = False) -> dict:
    """
    Трансформирует метаданные, добавляя объект 'image' согласно интерфейсу IDrawingResponse.
    all_pages=False: добавляет только первую страницу (для списков).
    all_pages=True: добавляет все страницы (для детального просмотра).
    """
    file_path = drawing_meta.get("file_path")
    # Инициализируем структуру по умолчанию
    drawing_meta["image"] = None

    if file_path and os.path.exists(file_path):
        try:
            pages = file_to_images_base64(file_path)
            if pages:
                # Формируем объект согласно запросу фронтенда
                drawing_meta["image"] = {
                    "base64": pages if all_pages else [pages[0]],
                    "total_pages": len(pages),
                    "content_type": "image/png"
                }
        except Exception as e:
            logger.warning(f"Ошибка при генерации изображения для {file_path}: {e}")

    return drawing_meta


# --- 1. Поиск и метаданные ---

@app.get("/api/drawings")
async def get_all_drawings(limit: int = 20, offset: int = 0):
    """Возвращает список чертежей с объектом image (превью первой страницы)."""
    collection = db_manager.collection
    cursor = collection.find({}, {"_id": 0})
    results = await cursor.skip(offset).limit(limit).to_list(length=limit)

    # Обогащаем каждый элемент списка объектом image
    enriched_results = [inject_image_data(d, all_pages=False) for d in results]

    total = await collection.count_documents({})
    return {"total": total, "drawings": enriched_results}


@app.get("/api/drawings/{drawing_id}")
async def get_drawing_by_id(drawing_id: str):
    """Детальная информация: объект image содержит массив всех страниц."""
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертеж не найден")

    # Здесь возвращаем все страницы чертежа внутри объекта image
    return inject_image_data(meta, all_pages=True)


@app.get("/api/search")
async def search_drawings(q: str, limit: int = 10, drawing_id: Optional[str] = None):
    """Поиск по векторной базе с обогащением метаданных (поле image)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            payload = {"query": q, "limit": limit}
            if drawing_id:
                meta_local = await get_drawing(drawing_id)
                if meta_local:
                    payload["path"] = meta_local.get("file_path")

            response = await client.post(f"{AGENT_URL}/search", json=payload)
            response.raise_for_status()
            search_results = response.json()

            for item in search_results.get("results", []):
                d_id = item.get("drawing_id")
                if d_id:
                    meta = await get_drawing(d_id)
                    if meta:
                        # В поиске обычно достаточно превью
                        item["metadata"] = inject_image_data(meta, all_pages=False)

            return search_results
        except Exception as e:
            logger.error(f"Agent search error: {e}")
            raise HTTPException(status_code=500, detail=f"Ошибка поиска: {str(e)}")


# --- 2. Загрузка и удаление ---

@app.post("/api/upload")
async def upload_drawing(file: UploadFile = File(...)):
    """Загрузка и мгновенный ответ с объектом image."""
    drawing_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1]
    save_path = os.path.join(UPLOAD_DIR, f"{drawing_id}{ext}")

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    drawing = {
        "id": drawing_id,
        "filename": file.filename,
        "status": "processing",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "file_path": save_path,
        "messages": [],
        "description": None,
        "has_embedding": True  # Указываем для соответствия интерфейсу
    }

    await save_drawing(drawing)
    celery_process_task.delay(drawing_id, "Сделай подробное техническое описание чертежа.")

    # Возвращаем созданный объект с превью
    return inject_image_data(drawing, all_pages=False)


@app.delete("/api/drawings/{drawing_id}")
async def delete_drawing_by_id(drawing_id: str):
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертеж не найден")

    if os.path.exists(meta.get("file_path")):
        os.remove(meta["file_path"])

    async with httpx.AsyncClient() as client:
        try:
            await client.delete(f"{AGENT_URL}/cache/{drawing_id}")
        except:
            pass

    await delete_drawing(drawing_id)
    return {"message": "Удалено успешно"}

# --- 3. WebSocket ---

@app.websocket("/ws/{drawing_id}")
async def websocket_endpoint(websocket: WebSocket, drawing_id: str):
    """
    Точка входа для сокета. Клиент подключается к конкретному drawing_id
    и ждет обновлений от системы.
    """
    await manager.connect(websocket, drawing_id)
    logger.info(f"WebSocket connected for drawing: {drawing_id}")

    try:
        while True:
            # Нам не нужно ничего принимать от клиента в чате через сокеты,
            # но мы держим соединение открытым.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, drawing_id)
        logger.info(f"WebSocket disconnected for drawing: {drawing_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, drawing_id)