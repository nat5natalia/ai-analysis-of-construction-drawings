"""
Система анализа строительных чертежей — FastAPI бэкенд
Запуск: uvicorn main:app --reload
Документация: http://localhost:8000/docs
"""
 
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uuid
import os
from datetime import datetime, timezone

# Импорты из наших модулей
from db import save_drawing, get_drawing, update_drawing, get_all_with_embeddings, delete_drawing
from ds import generate_description, answer_question, compute_embedding
from vector_db import vector_db

app = FastAPI(
    title="Анализ строительных чертежей",
    description="API для загрузки и анализа чертежей с помощью AI",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,   # или удалить эту строку
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)



 
class AskRequest(BaseModel):
    question: str




async def process_drawing(drawing_id: str):
    """
    Фоновая задача: генерирует описание, эмбеддинг и сохраняет их в БД и векторную БД.
    """
    meta = await get_drawing(drawing_id)
    if not meta:
        print(f"Чертёж {drawing_id} не найден при фоновой обработке.")
        return

    # Генерируем описание и эмбеддинг
    description = generate_description(meta["file_path"])
    embedding = compute_embedding(description)

    # Обновляем MongoDB
    await update_drawing(drawing_id, {
        "description": description,
        "embedding": embedding,
        "status": "processed"
    })

    # Сохраняем эмбеддинг в векторную БД
    vector_db.add(drawing_id, embedding)

    print(f"Чертёж {drawing_id} обработан.")




# --- 1. Загрузка чертежа ---------------------------------------------------

@app.post("/api/upload", summary="Загрузить чертёж")
async def upload_drawing(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    ALLOWED_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/tiff"}
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемый формат: {file.content_type}. Разрешены: PDF, PNG, JPEG, TIFF."
        )
 
    drawing_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1]
    save_path = os.path.join(UPLOAD_DIR, f"{drawing_id}{ext}")
 
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Файл превышает 50 МБ.")
 
    with open(save_path, "wb") as f:
        f.write(content)
 
    drawing = {
        "id": drawing_id,
        "filename": file.filename,
        "status": "uploaded",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "file_path": save_path,
        "description": None,
        "embedding": None,
    }
    await save_drawing(drawing)

    # Запускаем фоновую обработку
    if background_tasks:
        background_tasks.add_task(process_drawing, drawing_id)
    else:
        # Если BackgroundTasks не передан (например, при тестировании), запускаем синхронно
        await process_drawing(drawing_id)
 
    return {
        "id": drawing_id,
        "filename": file.filename,
        "status": "uploaded",
        "uploaded_at": drawing["uploaded_at"],
    }


# --- 2. Описание чертежа ---------------------------------------------------

@app.get("/api/describe/{drawing_id}", summary="Получить описание чертежа")
async def describe_drawing(drawing_id: str):
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертёж не найден.")
 
    if meta.get("description") is None:
        # Если описания нет (например, фоновая обработка ещё не завершилась)
        raise HTTPException(status_code=409, detail="Чертёж ещё обрабатывается, попробуйте позже.")
 
    return {
        "id": drawing_id,
        "description": meta["description"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cached": True,
    }


# --- 3. Вопрос по чертежу --------------------------------------------------
 
@app.post("/api/ask/{drawing_id}", summary="Задать вопрос по чертежу")
async def ask_about_drawing(drawing_id: str, body: AskRequest):
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертёж не найден.")
 
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Вопрос не может быть пустым.")
 
    # Для ответа используем DS-функцию (можно использовать описание как контекст)
    # Здесь можно реализовать RAG: взять описание чертежа и ответить.
    answer = answer_question(meta["file_path"], body.question)
 
    return {
        "id": drawing_id,
        "question": body.question,
        "answer": answer,
        "answered_at": datetime.now(timezone.utc).isoformat(),
    }
 
 
# --- 4. Текстовый поиск ----------------------------------------------------
 
@app.get("/api/search", summary="Поиск чертежей по тексту")
async def search_drawings(q: str, limit: int = 10, offset: int = 0):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Поисковый запрос не может быть пустым.")
 
    query_embedding = compute_embedding(q)
    # Ищем все подходящие элементы (максимум 1000, можно увеличить)
    all_results = vector_db.search(query_embedding, k=1000)
    
    # Получаем метаданные для текущей страницы
    page_results = []
    for drawing_id, score in all_results[offset:offset+limit]:
        meta = await get_drawing(drawing_id)
        if meta:
            desc = meta.get("description") or ""
            page_results.append({
                "id": drawing_id,
                "filename": meta["filename"],
                "description": desc[:200] + "..." if len(desc) > 200 else desc,
                "score": round(score, 4),
            })
 
    return {
        "total": len(all_results),  # общее число подходящих чертежей
        "results": page_results,
    }
 
 
# --- 5. Похожие чертежи ----------------------------------------------------
 
@app.get("/api/similar/{drawing_id}", summary="Найти похожие чертежи")
async def find_similar(drawing_id: str, limit: int = 5):
    source = await get_drawing(drawing_id)
    if not source:
        raise HTTPException(status_code=404, detail="Чертёж не найден.")
 
    if not source.get("embedding"):
        raise HTTPException(
            status_code=422,
            detail="Нет эмбеддинга. Возможно, чертёж ещё обрабатывается."
        )
 
    # Ищем похожие в векторной БД (исключая сам чертёж)
    results = vector_db.search(source["embedding"], k=limit+1)
    similar = []
    for other_id, similarity in results:
        if other_id == drawing_id:
            continue
        meta = await get_drawing(other_id)
        if meta:
            desc = meta.get("description") or ""
            similar.append({
                "id": other_id,
                "filename": meta["filename"],
                "description": desc[:200] + "..." if len(desc) > 200 else desc,
                "similarity": round(similarity, 4),
            })
        if len(similar) >= limit:
            break
 
    return {
        "source_id": drawing_id,
        "similar": similar,
    }
 
 
# --- 6. Список всех чертежей -----------------------------------------------

@app.get("/api/drawings", summary="Получить список всех чертежей")
async def get_drawings(limit: int = 20, offset: int = 0):
    """
    Возвращает список всех загруженных чертежей из базы с пагинацией.
    """
    from db import drawings  # импортируем коллекцию
    cursor = drawings.find({}, {"_id": 0, "id": 1, "filename": 1, "status": 1, "uploaded_at": 1, "description": 1})
    cursor = cursor.skip(offset).limit(limit)
    all_drawings = await cursor.to_list(length=limit)

    result = []
    for d in all_drawings:
        result.append({
            "id": d["id"],
            "filename": d["filename"],
            "status": d["status"],
            "uploaded_at": d["uploaded_at"],
            "has_description": d.get("description") is not None,
        })

    # Для total count делаем отдельный запрос
    total = await drawings.count_documents({})

    return {
        "total": total,
        "drawings": result,
    }


# --- 7. Один чертёж по ID --------------------------------------------------

@app.get("/api/drawings/{drawing_id}", summary="Получить чертёж по ID")
async def get_drawing_by_id(drawing_id: str):
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертёж не найден.")

    return {
        "id": meta["id"],
        "filename": meta["filename"],
        "status": meta["status"],
        "uploaded_at": meta["uploaded_at"],
        "description": meta.get("description"),
        "has_embedding": meta.get("embedding") is not None,
    }


# --- 8. Удаление чертежа ---------------------------------------------------

@app.delete("/api/drawings/{drawing_id}", summary="Удалить чертёж")
async def delete_drawing_by_id(drawing_id: str):
    meta = await get_drawing(drawing_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Чертёж не найден.")

    # Удаляем файл
    if os.path.exists(meta["file_path"]):
        os.remove(meta["file_path"])

    # Удаляем из MongoDB
    from db import drawings
    await drawings.delete_one({"id": drawing_id})



    return {"message": "Чертёж удалён"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)