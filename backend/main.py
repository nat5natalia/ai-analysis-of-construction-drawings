from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import os
import httpx  # Используем для быстрых запросов к Агенту
from datetime import datetime, timezone

from celery_worker.worker import process_drawing as celery_process_task
from db import save_drawing, get_drawing, drawings

app = FastAPI(
    title="Анализ строительных чертежей",
    description="API с поддержкой Celery и векторного поиска",
    version="1.2.0"
)

# Настройки связи с Агентом
AGENT_URL = os.getenv("AGENT_URL", "http://drawing-agent:8000")
UPLOAD_DIR = os.getenv("DATASET_PATH", "uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str


# --- 1. Поиск (Новое!) -----------------------------------------------------

@app.get("/api/search", summary="Семантический поиск по чертежам")
async def search_drawings(q: str, limit: int = 10):
    """
    Прокси-запрос к Агенту для поиска через FAISS
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="Запрос пуст")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Агент должен иметь эндпоинт /search
            response = await client.post(f"{AGENT_URL}/search", json={"query": q, "limit": limit})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ошибка векторного поиска: {str(e)}")


@app.get("/api/similar/{drawing_id}", summary="Найти визуально похожие")
async def find_similar(drawing_id: str, limit: int = 5):
    """
    Прокси-запрос к Агенту для поиска похожих векторов
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Агент должен иметь эндпоинт /similar/{id}
            response = await client.get(f"{AGENT_URL}/similar/{drawing_id}", params={"limit": limit})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail="Агент не смог найти похожие чертежи.")


# --- 2. Загрузка и Вопросы (Celery) ----------------------------------------

@app.post("/api/upload")
async def upload_drawing(file: UploadFile = File(...)):
    # ... (код валидации типов остается прежним)
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
        "description": None,
    }
    await save_drawing(drawing)

    # Асинхронная задача на первичное описание и индексацию в FAISS
    celery_process_task.delay(drawing_id, "Сделай техническое описание чертежа.")

    return {"id": drawing_id, "status": "processing"}


@app.post("/api/ask/{drawing_id}")
async def ask_about_drawing(drawing_id: str, body: AskRequest):
    meta = await get_drawing(drawing_id)
    if not meta: raise HTTPException(status_code=404)

    # Отправляем в очередь Celery
    task = celery_process_task.delay(drawing_id, body.question)
    return {"id": drawing_id, "task_id": task.id, "status": "queued"}


# --- 3. CRUD (Без изменений) -----------------------------------------------

@app.get("/api/drawings")
async def get_drawings(limit: int = 20, offset: int = 0):
    cursor = drawings.find({}, {"_id": 0, "id": 1, "filename": 1, "status": 1, "uploaded_at": 1, "description": 1})
    results = await cursor.skip(offset).limit(limit).to_list(length=limit)
    return {"total": await drawings.count_documents({}), "drawings": results}


@app.get("/api/drawings/{drawing_id}")
async def get_drawing_by_id(drawing_id: str):
    meta = await get_drawing(drawing_id)
    if not meta: raise HTTPException(status_code=404)
    return meta


@app.delete("/api/drawings/{drawing_id}")
async def delete_drawing_by_id(drawing_id: str):
    meta = await get_drawing(drawing_id)
    if not meta: raise HTTPException(status_code=404)
    if os.path.exists(meta["file_path"]): os.remove(meta["file_path"])
    await drawings.delete_one({"id": drawing_id})
    # Опционально: отправить задачу Агенту на удаление из FAISS
    return {"message": "Удалено"}