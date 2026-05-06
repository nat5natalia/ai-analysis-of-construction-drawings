from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import os
import httpx
from datetime import datetime, timezone

# Импортируем ТОЛЬКО нужное из db.py
from db import save_drawing, get_drawing, db_manager

# Celery-воркер не импортируем напрямую, чтобы не вызывать ошибок
# Вместо этого делаем заглушку и будем вызывать через HTTP при необходимости
try:
    from celery_worker.worker import process_drawing as celery_process_task
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    celery_process_task = None
    print("Warning: Celery worker not available, tasks will be queued via HTTP")

app = FastAPI(
    title="Анализ строительных чертежей",
    description="API с поддержкой Celery и векторного поиска",
    version="1.2.1"
)

# CORS middleware (только один раз!)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Принудительные CORS-заголовки для всех ответов
@app.middleware("http")
async def force_cors(request, call_next):
    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

# Настройки
AGENT_URL = os.getenv("AGENT_URL", "http://drawing-agent:8000")
UPLOAD_DIR = os.getenv("DATASET_PATH", "uploads")

# Создаем папку для загрузок, если её нет
os.makedirs(UPLOAD_DIR, exist_ok=True)


class AskRequest(BaseModel):
    question: str


@app.on_event("startup")
async def startup_event():
    """Подключаемся к БД при старте"""
    await db_manager.connect()
    print("Backend started, database connected")


async def get_collection():
    """Вспомогательная функция для получения коллекции"""
    if db_manager.collection is None:
        await db_manager.connect()
    return db_manager.collection


# --- 1. Поиск и метаданные ---

@app.get("/api/drawings")
async def get_all_drawings(limit: int = 20, offset: int = 0):
    collection = await get_collection()
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

    # Сохраняем файл на диск
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

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

    # Отправляем задачу в Celery (если доступен)
    if CELERY_AVAILABLE and celery_process_task:
        try:
            celery_process_task.delay(drawing_id, "Сделай техническое описание чертежа.")
        except Exception as e:
            print(f"Failed to dispatch Celery task: {e}")
            collection = await get_collection()
            await collection.update_one(
                {"id": drawing_id},
                {"$set": {"status": "queued_failed", "error": f"Broker error: {str(e)}"}}
            )
    else:
        print(f"Celery not available, task for {drawing_id} not queued")

    return {"id": drawing_id, "status": "processing"}


@app.post("/api/ask/{drawing_id}")
async def ask_about_drawing(drawing_id: str, body: AskRequest):
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертеж не найден")

    # Отправляем вопрос в очередь (если Celery доступен)
    if CELERY_AVAILABLE and celery_process_task:
        try:
            task = celery_process_task.delay(drawing_id, body.question)
            return {"id": drawing_id, "task_id": task.id, "status": "queued"}
        except Exception as e:
            print(f"Failed to dispatch Celery task for question: {e}")
            collection = await get_collection()
            await collection.update_one(
                {"id": drawing_id},
                {"$set": {"status": "queued_failed", "error": f"Broker error: {str(e)}"}}
            )
            raise HTTPException(status_code=503, detail=f"Failed to queue task: {str(e)}")
    else:
        return {
            "id": drawing_id,
            "status": "celery_unavailable",
            "detail": "Celery worker not configured, task not queued"
        }


# --- 3. Удаление ---

@app.delete("/api/drawings/{drawing_id}")
async def delete_drawing_by_id(drawing_id: str):
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертеж не найден")

    if os.path.exists(meta["file_path"]):
        os.remove(meta["file_path"])

    collection = await get_collection()
    await collection.delete_one({"id": drawing_id})
    return {"message": "Удалено успешно"}


# --- 4. Прокси-запросы к Агенту (Поиск) ---

@app.get("/api/search")
async def search_drawings(q: str, limit: int = 10):
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(f"{AGENT_URL}/search", json={"query": q, "limit": limit})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Agent error (HTTP {e.response.status_code}): {e.response.text}"
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ошибка Агента: {str(e)}")