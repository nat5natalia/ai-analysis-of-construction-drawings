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
            # Создаем клиент внутри работающего event loop
            self.client = AsyncIOMotorClient(self.url)
            self.db = self.client[self.db_name]
            self._collection = self.db["drawings"]
            print(f"Connected to MongoDB: {self.db_name}")

    @property
    def collection(self):
        """Безопасный доступ к коллекции"""
        if self._collection is None:
            # Если мы обратились к коллекции до вызова connect(),
            # это сигнализирует о проблеме в жизненном цикле приложения
            raise RuntimeError("Database not connected. Call 'await db_manager.connect()' first.")
        return self._collection

# Создаем экземпляр
db_manager = MongoDB()

async def save_drawing(drawing: dict):
    """Сохранение чертежа"""
    await db_manager.connect()  # Гарантируем наличие подключения
    result = await db_manager.collection.insert_one(drawing)
    return str(result.inserted_id)

async def get_drawing(drawing_id: str):
    """Получение чертежа по ID"""
    await db_manager.connect()
    # Пытаемся искать и по строковому id, и по ObjectId (на всякий случай)
    try:
        query = {"id": drawing_id}
        result = await db_manager.collection.find_one(query, {"_id": 0})
        if not result:
            # Если в базе хранятся стандартные Mongo ObjectId
            result = await db_manager.collection.find_one({"_id": ObjectId(drawing_id)})
        return result
    except Exception:
        return await db_manager.collection.find_one({"id": drawing_id}, {"_id": 0})

# Для обратной совместимости, если где-то в коде осталось обращение к 'drawings'
# Но лучше везде использовать db_manager.collection
drawings = db_manager