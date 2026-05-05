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

# Lazy getter function for drawings collection
def get_drawings_collection():
    """Get drawings collection, ensuring connection is initialized"""
    db_manager.connect()
    return db_manager.collection

# Export as 'drawings' for backward compatibility - this will be a module-level callable
# that returns the collection after ensuring connection
class _DrawingsProxy:
    """Proxy object that ensures connection before accessing collection"""
    def __getattr__(self, name):
        db_manager.connect()
        return getattr(db_manager.collection, name)

drawings = _DrawingsProxy()

async def save_drawing(drawing: dict):
    db_manager.connect()
    await db_manager.collection.insert_one(drawing)

async def get_drawing(drawing_id: str):
    db_manager.connect()
    return await db_manager.collection.find_one({"id": drawing_id}, {"_id": 0})
