import os
from motor.motor_asyncio import AsyncIOMotorClient

class MongoDB:
    def __init__(self):
        self.client = None
        self.db = None
        self.collection = None
        self.url = os.getenv("MONGO_URL", "mongodb://mongodb:27017")
        self.db_name = os.getenv("MONGO_DB", "drawings_db")

    def connect(self):
        """Инициализация подключения"""
        if not self.client:
            self.client = AsyncIOMotorClient(self.url)
            self.db = self.client[self.db_name]
            self.collection = self.db["drawings"]
            print(f"Connected to MongoDB: {self.db_name}")

# Создаем экземпляр
db_manager = MongoDB()

async def save_drawing(drawing: dict):
    db_manager.connect()
    await db_manager.collection.insert_one(drawing)

async def get_drawing(drawing_id: str):
    db_manager.connect()
    return await db_manager.collection.find_one({"id": drawing_id}, {"_id": 0})

db_manager = MongoDB()
db_manager.connect() # Подключаемся при старте модуля

# Экспортируем переменную для main.py
drawings = db_manager.collection

async def save_drawing(drawing: dict):
    await drawings.insert_one(drawing)

async def get_drawing(drawing_id: str):
    return await drawings.find_one({"id": drawing_id}, {"_id": 0})