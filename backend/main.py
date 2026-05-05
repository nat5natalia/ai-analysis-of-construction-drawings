from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import os
import httpx
from datetime import datetime, timezone

# Импортируем нашу обновленную логику БД
from db import save_drawing, get_drawing, drawings, db_manager
from celery_worker.worker import process_drawing as celery_process_task

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
    # Инициализируем подключение к БД при старте
    db_manager.connect()


# --- 1. Поиск и метаданные ---

@app.get("/api/drawings")
async def get_all_drawings(limit: int = 20, offset: int = 0):
    # Используем переменную drawings, которую мы экспортировали из db.py
    cursor = drawings.find({}, {"_id": 0})
    results = await cursor.skip(offset).limit(limit).to_list(length=limit)
    total = await drawings.count_documents({})
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

    # ВАЖНО: Ждем фактического завершения записи в БД
    await save_drawing(drawing)

    # Проверочный запрос: гарантируем, что запись "видна"
    # Это решает проблему, когда воркер стартует быстрее, чем БД обновит индекс
    for _ in range(3):  # 3 попытки убедиться
        check = await get_drawing(drawing_id)
        if check:
            break

    # Отправляем задачу в Celery только когда запись точно в базе
    celery_process_task.delay(drawing_id, "Сделай техническое описание чертежа.")

    return {"id": drawing_id, "status": "processing"}


@app.post("/api/ask/{drawing_id}")
async def ask_about_drawing(drawing_id: str, body: AskRequest):
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертеж не найден")

    # Отправляем вопрос в очередь
    task = celery_process_task.delay(drawing_id, body.question)
    return {"id": drawing_id, "task_id": task.id, "status": "queued"}


# --- 3. Удаление ---

@app.delete("/api/drawings/{drawing_id}")
async def delete_drawing_by_id(drawing_id: str):
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404)

    if os.path.exists(meta["file_path"]):
        os.remove(meta["file_path"])

    await drawings.delete_one({"id": drawing_id})
    return {"message": "Удалено успешно"}


# --- 4. Прокси-запросы к Агенту (Поиск) ---

@app.get("/api/search")
async def search_drawings(q: str, limit: int = 10):
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(f"{AGENT_URL}/search", json={"query": q, "limit": limit})
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ошибка Агента: {str(e)}")