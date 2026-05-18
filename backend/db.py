import os
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId


class MongoDB:
    """
    Класс-менеджер для управления жизненным циклом подключений к MongoDB.
    Использует Motor для асинхронного взаимодействия.
    """

    def __init__(self):
        self.client = None
        self.db = None
        self._collection = None
        # Параметры подключения из переменных окружения (настраиваются в docker-compose)
        self.url = os.getenv("MONGO_URL", "mongodb://mongodb:27017")
        self.db_name = os.getenv("MONGO_DB", "drawings_db")

    async def connect(self):
        """
        Инициализирует пул соединений с базой.
        Вызывается один раз при старте приложения (startup_event).
        """
        if not self.client:
            self.client = AsyncIOMotorClient(self.url)
            self.db = self.client[self.db_name]
            self._collection = self.db["drawings"]
            await self._collection.create_index(
                "file_hash",
                unique=True,
                sparse=True,
                name="unique_file_hash"
            )
            print(f" Успешное подключение к MongoDB: {self.db_name}")

    @property
    def collection(self):
        """Обеспечивает безопасный доступ к коллекции документов."""
        if self._collection is None:
            raise RuntimeError("База данных не подключена. Сначала вызовите 'await db_manager.connect()'")
        return self._collection


# Глобальный экземпляр для импорта в других модулях
db_manager = MongoDB()


async def save_drawing(drawing: dict):
    """
    Сохраняет метаданные чертежа (ID, путь к файлу, статус) в БД.
    Сами изображения страниц в базу не пишутся — они генерируются бэкендом из файла.
    """
    await db_manager.connect()
    result = await db_manager.collection.insert_one(drawing)
    return str(result.inserted_id)


async def get_drawing(drawing_id: str):
    """
    Поиск чертежа. Сначала ищет по кастомному UUID (поле 'id'),
    затем пробует стандартный системный '_id' от MongoDB.
    """
    await db_manager.connect()

    try:
        query = {"id": drawing_id}
        result = await db_manager.collection.find_one(query, {"_id": 0})
        if not result:
            result = await db_manager.collection.find_one({"_id": ObjectId(drawing_id)})
        return result
    except Exception:
        return await db_manager.collection.find_one({"id": drawing_id}, {"_id": 0})


async def delete_drawing(drawing_id: str):
    """Удаляет запись о чертеже из коллекции."""
    await db_manager.connect()
    # Удаляем именно по нашему UUID, который создается в бэкенде
    result = await db_manager.collection.delete_one({"id": drawing_id})
    return result.deleted_count > 0


# Псевдоним для удобства, если где-то используется старое название
drawings = db_manager
