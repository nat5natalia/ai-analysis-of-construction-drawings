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

executor = ThreadPoolExecutor(max_workers=4)

app = FastAPI(
    title="Анализ строительных чертежей",
    description="Оптимизированная версия 1.7.2: Исправлена передача ответов в WebSocket",
    version="1.7.2"
)

app.mount("/static", StaticFiles(directory=UPLOAD_DIR), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Схемы ---
class MessageSchema(BaseModel):
    role: str
    text: Optional[str] = None    # Делаем Optional, чтобы старые записи не ломали API
    content: Optional[str] = None # Поле, которое уже есть в твоей БД
    ts: str

    # Добавляем валидатор, чтобы если есть только content, он попадал в text
    model_config = ConfigDict(from_attributes=True, extra="ignore")

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
    messages: List[MessageSchema] = []
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
        while True:
            message = await pubsub.get_message()
            if message and message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    d_id = data.get("drawing_id")

                    # Если в данных есть реальный ответ — формируем объект сообщения
                    if data.get("event") == "new_message" and data.get("answer"):
                        data["message"] = {
                            "role": "assistant",
                            "text": data["answer"],
                            "content": data["answer"],
                            "ts": datetime.now(timezone.utc).isoformat()
                        }

                    if d_id:
                        # Отправляем в сокет (менеджер сам проверит наличие подписки)
                        await manager.send_to_drawing(data, d_id)

                except Exception as e:
                    logger.error(f"Error processing Redis message: {e}")
            await asyncio.sleep(0.01)
    except Exception as e:
        logger.critical(f"Redis Listener failure: {e}")
    finally:
        await pubsub.unsubscribe("drawing_updates")
        await r.close()

@app.on_event("startup")
async def startup_event():
    await db_manager.connect()
    asyncio.create_task(redis_listener())
    logger.info("Backend services started")


# --- Вспомогательная логика ---

async def inject_image_data(drawing_meta: dict, all_pages: bool = False) -> dict:
    file_path = drawing_meta.get("file_path")

    if file_path and os.path.exists(file_path):
        try:
            loop = asyncio.get_event_loop()
            # Конвертируем PDF в список base64
            pages = await loop.run_in_executor(executor, file_to_images_base64, file_path)

            if pages:
                # Если all_pages=True — отдаем всё, иначе — только первую страницу
                result_pages = pages if all_pages else pages[:1]

                drawing_meta["image"] = {
                    "base64": result_pages,
                    "total_pages": len(pages),  # Оставляем реальное кол-во страниц для информации
                    "content_type": "image/png"
                }
            else:
                drawing_meta["image"] = None

        except Exception as e:
            logger.warning(f"Image injection failed for {drawing_meta.get('id')}: {e}")
            drawing_meta["image"] = None
    else:
        drawing_meta["image"] = None

    return drawing_meta

# --- API Эндпоинты ---

@app.get("/api/drawings", response_model=DrawingsListResponse)
async def get_all_drawings(limit: int = 50, offset: int = 0):
    collection = db_manager.collection
    cursor = collection.find({}, {"_id": 0}).sort("uploaded_at", -1)
    raw_results = await cursor.skip(offset).limit(limit).to_list(length=limit)

    # Обогащаем каждый чертеж данными изображений
    enriched_results = []
    for meta in raw_results:
        # Ставим all_pages=True, если фронту нужны все страницы сразу в списке
        # Если список тяжелый, можно оставить False (будет только мета)
        enriched = await inject_image_data(meta, all_pages=True)
        enriched_results.append(enriched)

    total = await collection.count_documents({})
    return {"total": total, "drawings": enriched_results}


@app.get("/api/drawings/{drawing_id}", response_model=DrawingResponse)
async def get_drawing_by_id(drawing_id: str):
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертеж не найден")
    enriched = await inject_image_data(meta, all_pages=True)
    return enriched


@app.get("/api/search")
async def search_drawings(q: str, limit: int = 10, offset: int = 0):
    results = []
    seen_ids = set()

    # --- 1. Попытка векторного поиска через Агента ---
    try:
        async with httpx.AsyncClient() as client:
            agent_payload = {
                "query": q,
                "limit": limit * 2,
                "drawing_id": None
            }
            agent_resp = await client.post(
                f"{AGENT_URL}/search",
                json=agent_payload,
                timeout=15.0
            )
            if agent_resp.status_code == 200:
                agent_data = agent_resp.json()
                agent_results = agent_data.get("results", [])

                for match in agent_results:
                    d_id = match.get("drawing_id")
                    if not d_id or d_id in seen_ids:
                        continue

                    meta = await get_drawing(d_id)
                    if meta:
                        seen_ids.add(d_id)
                        enriched = await inject_image_data(meta, all_pages=False)
                        results.append({
                            "id": enriched.get("id"),
                            "filename": enriched.get("filename"),
                            "description": (match.get("text") or enriched.get("description", ""))[:200] + "...",
                            "score": match.get("score", 0.0),
                            "thumbnail_url": enriched.get("thumbnail_url"),
                            "image": enriched.get("image"),
                            "search_type": "vector"
                        })
    except Exception as e:
        logger.error(f"Vector search failed, switching to regex: {e}")

    # --- 2. Fallback: Регулярки в MongoDB (если векторный поиск дал 0 или упал) ---
    if not results:
        logger.info(f"Vector search returned 0 results for '{q}'. Starting Regex search...")
        try:
            # Создаем нечувствительное к регистру регулярное выражение
            regex_query = {"$regex": q, "$options": "i"}

            # Ищем совпадения либо в названии файла, либо в описании
            mongo_query = {
                "$or": [
                    {"filename": regex_query},
                    {"description": regex_query}
                ]
            }

            collection = db_manager.collection
            cursor = collection.find(mongo_query, {"_id": 0}).sort("uploaded_at", -1)
            db_matches = await cursor.skip(offset).limit(limit).to_list(length=limit)

            for meta in db_matches:
                d_id = meta.get("id")
                if d_id not in seen_ids:
                    seen_ids.add(d_id)
                    enriched = await inject_image_data(meta, all_pages=False)
                    results.append({
                        "id": enriched.get("id"),
                        "filename": enriched.get("filename"),
                        "description": (enriched.get("description") or "Описание отсутствует")[:200] + "...",
                        "score": 1.0,  # Условный скор для регулярок
                        "thumbnail_url": enriched.get("thumbnail_url"),
                        "image": enriched.get("image"),
                        "search_type": "regex"
                    })
        except Exception as e:
            logger.error(f"Regex search failed: {e}")

    return {
        "total": len(results),
        "results": results,
        "query": q,
        "is_fallback": len(results) > 0 and any(r.get("search_type") == "regex" for r in results)
    }

@app.post("/api/upload", response_model=DrawingResponse)
async def upload_drawing(file: UploadFile = File(...)):
    drawing_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1]
    save_path = os.path.join(UPLOAD_DIR, f"{drawing_id}{ext}")
    thumb_path = os.path.join(UPLOAD_DIR, f"{drawing_id}_thumb.jpg")

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(executor, save_pdf_thumbnail, save_path, thumb_path)
        thumbnail_url = f"/static/{drawing_id}_thumb.jpg"
    except:
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
    return await inject_image_data(drawing, all_pages=True)

@app.post("/api/ask/{drawing_id}")
async def ask_question(drawing_id: str, request: AskRequest):
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертеж не найден")

    ts = datetime.now(timezone.utc).isoformat()
    # Формируем сообщение строго по интерфейсу IMessage
    new_msg = {
        "role": "user",
        "text": request.question,    # Добавляем текстовое поле
        "content": request.question,
        "ts": ts
    }
    logger.info(f"DEBUG DB: Saving user question for ID={drawing_id}. Text: {request.question[:30]}...")
    await db_manager.collection.update_one(
        {"id": drawing_id},
        {
            "$set": {"status": "processing", "last_ask_at": ts},
            "$push": {"messages": new_msg}
        }
    )

    # Отправляем в сокет сразу, чтобы пользователь видел свой вопрос
    await manager.send_to_drawing({
        "drawing_id": drawing_id,
        "status": "processing",
        "event": "new_message",
        "message": new_msg # Передаем объект сообщения
    }, drawing_id)

    celery_process_task.delay(drawing_id, request.question)
    return {"status": "queued"}


@app.delete("/api/drawings/{drawing_id}")
async def delete_drawing_by_id(drawing_id: str):
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертеж не найден")

    for f in [meta.get("file_path"), os.path.join(UPLOAD_DIR, f"{drawing_id}_thumb.jpg")]:
        if f and os.path.exists(f):
            os.remove(f)

    async with httpx.AsyncClient() as client:
        try:
            await client.delete(f"{AGENT_URL}/cache/{drawing_id}", timeout=2.0)
        except:
            pass

    await delete_drawing(drawing_id)
    return {"message": "Удалено успешно", "id": drawing_id}


@app.websocket("/ws/{drawing_id}")
async def websocket_endpoint(websocket: WebSocket, drawing_id: str):
    await manager.connect(websocket, drawing_id)
    try:
        while True:
            # Ожидание данных от клиента (keep-alive или входящие команды)
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, drawing_id)
    except Exception:
        manager.disconnect(websocket, drawing_id)