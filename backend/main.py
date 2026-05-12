import os
import uuid
import httpx
import logging
import asyncio
import json
from datetime import datetime, timezone
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

# Импорты локальных модулей
from db import db_manager, save_drawing, get_drawing, delete_drawing
from celery_worker.worker import process_drawing as celery_process_task
from pdf import file_to_images_base64, save_pdf_thumbnail
from connection_manager import manager
import redis.asyncio as redis

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("DrawingBackend")

# --- Конфигурация ---
AGENT_URL = os.getenv("AGENT_URL", "http://drawing_agent:8000")
UPLOAD_DIR = os.getenv("DATASET_PATH", "uploads")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

os.makedirs(UPLOAD_DIR, exist_ok=True)

# Пул потоков для тяжелых задач (рендеринг PDF)
executor = ThreadPoolExecutor(max_workers=4)

app = FastAPI(
    title="Анализ строительных чертежей",
    description="Оптимизированная версия 1.7.0 с расширенным логированием",
    version="1.7.0"
)

# Раздаем статику для превью
app.mount("/static", StaticFiles(directory=UPLOAD_DIR), name="static")

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Схемы ---

class DrawingImage(BaseModel):
    base64: List[str]
    total_pages: int
    content_type: str = "image/png"


class DrawingResponse(BaseModel):
    id: str
    filename: str
    status: str
    uploaded_at: str
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    image: Optional[DrawingImage] = None

    model_config = ConfigDict(from_attributes=True, extra="ignore")


class DrawingsListResponse(BaseModel):
    total: int
    drawings: List[DrawingResponse]


class AskRequest(BaseModel):
    question: str


# --- Фоновая задача Redis ---

async def redis_listener():
    """Слушает уведомления от Celery и транслирует их в WebSocket"""
    logger.info(f"Connecting to Redis Pub/Sub at {REDIS_URL}...")
    r = redis.from_url(REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()

    try:
        await pubsub.subscribe("drawing_updates")
        logger.info("Successfully subscribed to 'drawing_updates' channel")

        while True:
            message = await pubsub.get_message(ignore_subscribe_message=True)
            if message:
                try:
                    data = json.loads(message["data"])
                    d_id = data.get("drawing_id")
                    logger.info(f"Received update from worker for ID: {d_id} | Status: {data.get('status')}")
                    if d_id:
                        await manager.send_to_drawing(data, d_id)
                except Exception as e:
                    logger.error(f"Error processing Redis message: {e}")
            await asyncio.sleep(0.01)
    except Exception as e:
        logger.critical(f"Redis Listener failure: {e}")
    finally:
        await r.close()
        logger.info("Redis connection closed")


@app.on_event("startup")
async def startup_event():
    logger.info("Initializing backend services...")
    await db_manager.connect()
    asyncio.create_task(redis_listener())
    logger.info("Backend is ready")


# --- Логика обработки изображений ---

async def inject_image_data(drawing_meta: dict, all_pages: bool = False) -> dict:
    """Обогащает данные Base64 для детального просмотра"""
    file_path = drawing_meta.get("file_path")
    if all_pages and file_path and os.path.exists(file_path):
        logger.info(f"Rendering PDF to Base64: {file_path}")
        try:
            loop = asyncio.get_event_loop()
            pages = await loop.run_in_executor(executor, file_to_images_base64, file_path)
            drawing_meta["image"] = {
                "base64": pages,
                "total_pages": len(pages),
                "content_type": "image/png"
            }
            logger.info(f"Rendering complete: {len(pages)} pages generated")
        except Exception as e:
            logger.warning(f"Failed to render PDF {file_path}: {e}")
    return drawing_meta


# --- API Эндпоинты ---

@app.get("/api/drawings", response_model=DrawingsListResponse)
async def get_all_drawings(limit: int = 50, offset: int = 0):
    logger.info(f"Fetching drawings list (limit={limit}, offset={offset})")
    collection = db_manager.collection
    cursor = collection.find({}).sort("uploaded_at", -1)
    raw_results = await cursor.skip(offset).limit(limit).to_list(length=limit)

    total = await collection.count_documents({})
    return {"total": total, "drawings": raw_results}


@app.get("/api/drawings/{drawing_id}", response_model=DrawingResponse)
async def get_drawing_by_id(drawing_id: str):
    logger.info(f"Fetching details for drawing: {drawing_id}")
    meta = await get_drawing(drawing_id)
    if not meta:
        logger.error(f"Drawing {drawing_id} not found in database")
        raise HTTPException(status_code=404, detail="Чертеж не найден")

    enriched = await inject_image_data(meta, all_pages=True)
    return enriched


@app.post("/api/upload", response_model=DrawingResponse)
async def upload_drawing(file: UploadFile = File(...)):
    drawing_id = str(uuid.uuid4())
    logger.info(f"Starting upload: {file.filename} -> assigned ID: {drawing_id}")

    ext = os.path.splitext(file.filename)[1]
    save_path = os.path.join(UPLOAD_DIR, f"{drawing_id}{ext}")
    thumb_path = os.path.join(UPLOAD_DIR, f"{drawing_id}_thumb.jpg")

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)
    logger.info(f"File saved to disk: {save_path}")

    # Генерация превью
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(executor, save_pdf_thumbnail, save_path, thumb_path)
        thumbnail_url = f"/static/{drawing_id}_thumb.jpg"
        logger.info(f"Thumbnail generated: {thumb_path}")
    except Exception as e:
        logger.error(f"Thumbnail generation failed for {drawing_id}: {e}")
        thumbnail_url = None

    drawing = {
        "id": drawing_id,
        "filename": file.filename,
        "status": "processing",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "file_path": save_path,
        "thumbnail_url": thumbnail_url,
        "messages": [],
        "description": None
    }

    await save_drawing(drawing)
    celery_process_task.delay(drawing_id, "Сделай подробное техническое описание чертежа.")
    logger.info(f"Primary analysis task sent to Celery for {drawing_id}")

    return drawing


@app.post("/api/ask/{drawing_id}")
async def ask_question(drawing_id: str, request: AskRequest):
    logger.info(f"User question for {drawing_id}: {request.question[:50]}...")

    meta = await get_drawing(drawing_id)
    if not meta:
        logger.error(f"Ask failed: Drawing {drawing_id} not found")
        raise HTTPException(status_code=404, detail="Чертеж не найден")

    ts = datetime.now(timezone.utc).isoformat()
    new_msg = {"role": "user", "content": request.question, "ts": ts}

    # 1. Сохранение в БД
    await db_manager.collection.update_one(
        {"id": drawing_id},
        {
            "$set": {"status": "processing", "last_ask_at": ts},
            "$push": {"messages": new_msg}
        }
    )

    # 2. Уведомление фронтенда
    await manager.send_to_drawing({
        "drawing_id": drawing_id,
        "event": "new_message",
        "message": new_msg,
        "status": "processing"
    }, drawing_id)
    logger.info(f"Pushing new message to WS for {drawing_id}")

    # 3. Задача в Celery
    celery_process_task.delay(drawing_id, request.question)
    logger.info(f"Question task queued in Celery for {drawing_id}")

    return {"status": "queued"}


@app.delete("/api/drawings/{drawing_id}")
async def delete_drawing_by_id(drawing_id: str):
    logger.info(f"Request to delete drawing: {drawing_id}")
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертеж не найден")

    # Чистка файлов
    for f in [meta.get("file_path"), os.path.join(UPLOAD_DIR, f"{drawing_id}_thumb.jpg")]:
        if f and os.path.exists(f):
            os.remove(f)
            logger.info(f"Deleted file: {f}")

    # Очистка кэша агента
    async with httpx.AsyncClient() as client:
        try:
            await client.delete(f"{AGENT_URL}/cache/{drawing_id}", timeout=2.0)
            logger.info(f"Agent cache cleared for {drawing_id}")
        except Exception as e:
            logger.warning(f"Could not clear agent cache: {e}")

    await delete_drawing(drawing_id)
    logger.info(f"Drawing {drawing_id} fully removed from system")
    return {"message": "Удалено успешно", "id": drawing_id}


@app.websocket("/ws/{drawing_id}")
async def websocket_endpoint(websocket: WebSocket, drawing_id: str):
    await manager.connect(websocket, drawing_id)
    logger.info(f"WebSocket established for drawing: {drawing_id}")
    try:
        while True:
            # Слушаем входящие сообщения (keep-alive)
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, drawing_id)
        logger.info(f"WebSocket disconnected for drawing: {drawing_id}")
    except Exception as e:
        logger.error(f"WebSocket error for {drawing_id}: {e}")
        manager.disconnect(websocket, drawing_id)