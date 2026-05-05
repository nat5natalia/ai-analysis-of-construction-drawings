import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os

MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongodb:27017")
DB_NAME = "drawings_db"

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
drawings = db["drawings"]

async def save_drawing(drawing: dict):
    # Бэкенд просто сохраняет метаданные.
    # Эмбеддинги добавит Агент позже через обновление.
    await drawings.insert_one(drawing)

async def get_drawing(drawing_id: str):
    return await drawings.find_one({"id": drawing_id}, {"_id": 0})

async def update_drawing(drawing_id: str, fields: dict):
    await drawings.update_one({"id": drawing_id}, {"$set": fields})

async def delete_drawing(drawing_id: str):
    await drawings.delete_one({"id": drawing_id})