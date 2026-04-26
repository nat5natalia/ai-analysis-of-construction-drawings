import asyncio
import hashlib
import numpy as np

from motor.motor_asyncio import AsyncIOMotorClient
from sentence_transformers import SentenceTransformer
from vector_db import VectorDB

MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "drawings_db"

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
model = SentenceTransformer(EMBEDDING_MODEL)
EMBEDDING_DIM = model.get_sentence_embedding_dimension()

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
drawings = db["drawings"]

vector_db = VectorDB(dimension=EMBEDDING_DIM)

def string_id_to_int64(s: str) -> int:
    """Преобразует строковый ID в 64-битное целое (для FAISS)."""
    h = hashlib.md5(s.encode()).hexdigest()
    # Берём первые 16 символов (8 байт) и превращаем в int64 со знаком
    return np.int64(int(h[:16], 16) & 0x7FFFFFFFFFFFFFFF)  # оставляем знаковый положительный

async def save_drawing(drawing: dict):
    print(">>> СОХРАНЯЕМ В MONGO:", drawing["id"])
    result = await drawings.insert_one(drawing)
    print(">>> СОХРАНЕНО, _id:", result.inserted_id)

    embedding = drawing.get("embedding")
    if embedding is not None and "id" in drawing:
        vec = np.array(embedding, dtype='float32').reshape(1, -1)
        num_id = string_id_to_int64(drawing["id"])
        # Выполняем синхронное добавление в потоке, чтобы не блокировать event loop
        await asyncio.to_thread(
            vector_db.add,
            vec,
            [num_id],
            [{"drawing_id": drawing["id"]}]   # метаданные
        )

async def get_drawing(drawing_id: str):
    return await drawings.find_one({"id": drawing_id})

async def update_drawing(drawing_id: str, fields: dict):
    await drawings.update_one({"id": drawing_id}, {"$set": fields})

async def get_all_with_embeddings():
    cursor = drawings.find({"embedding": {"$exists": True}})
    return await cursor.to_list(length=1000)

async def get_all_drawings():
    cursor = drawings.find({})
    return await cursor.to_list(length=1000)

async def delete_drawing(drawing_id: str):
    # Удаляем из MongoDB
    await drawings.delete_one({"id": drawing_id})
    # Удаляем из векторной базы
    num_id = string_id_to_int64(drawing_id)
    await asyncio.to_thread(vector_db.delete, [num_id])