import os
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

class MongoDB:
    def __init__(self):
        self.client = None
        self.db = None
        self._collection = None
        self.url = os.getenv("MONGO_URL", "mongodb://mongodb:27017")
        self.db_name = os.getenv("MONGO_DB", "drawings_db")

    async def connect(self):
        """Асинхронная инициализация подключения"""
        if not self.client:
            self.client = AsyncIOMotorClient(self.url)
            self.db = self.client[self.db_name]
            self._collection = self.db["drawings"]
            print(f"Connected to MongoDB: {self.db_name}")

    @property
    def collection(self):
        if self._collection is None:
            raise RuntimeError("Database not connected. Call 'await db_manager.connect()' first.")
        return self._collection

# Создаём экземпляр
db_manager = MongoDB()

async def save_drawing(drawing: dict):
    await db_manager.connect()
    result = await db_manager.collection.insert_one(drawing)
    return str(result.inserted_id)

async def get_drawing(drawing_id: str):
    await db_manager.connect()
    try:
        result = await db_manager.collection.find_one({"id": drawing_id}, {"_id": 0})
        if not result:
            result = await db_manager.collection.find_one({"_id": ObjectId(drawing_id)}, {"_id": 0})
        return result
    except Exception:
        return await db_manager.collection.find_one({"id": drawing_id}, {"_id": 0})