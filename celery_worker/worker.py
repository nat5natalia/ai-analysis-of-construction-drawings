import os
import requests
import logging
from celery import Celery
from pymongo import MongoClient

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация из окружения
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongodb:27017")
AGENT_URL = os.getenv("AGENT_URL", "http://drawing-agent:8000/process")

# Инициализация Celery
app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)

# MongoDB клиент (синхронный для воркера — это ок)
mongo_client = MongoClient(MONGO_URL)
db = mongo_client["construction_drawings"]
drawings_collection = db["drawings"]


@app.task(name="process_drawing")
def process_drawing(drawing_id: str, question: str):
    logger.info(f"Запуск задачи для чертежа {drawing_id}. Вопрос: {question}")

    # 1. Получаем данные из БД
    drawing = drawings_collection.find_one({"id": drawing_id})
    if not drawing:
        logger.error(f"Чертеж {drawing_id} не найден в БД")
        return {"error": "Not found"}

    # 2. Запрос к Агенту
    payload = {
        "path": drawing.get("file_path"),
        "question": question,
        "thread_id": drawing_id
    }

    try:
        # Таймаут 5 минут — для тяжелых чертежей это норма
        response = requests.post(AGENT_URL, json=payload, timeout=300)
        response.raise_for_status()
        result = response.json()

        if result.get("success"):
            status = "completed"
            answer = result.get("answer")
            error_msg = None
        else:
            status = "failed"
            answer = None
            error_msg = result.get("error")

    except Exception as e:
        logger.error(f"Ошибка при запросе к Агенту: {e}")
        status = "failed"
        answer = None
        error_msg = str(e)

    # 3. Обновление БД
    update_data = {
        "status": status,
        "error": error_msg,
        "last_answer": answer
    }

    # Если это первичный анализ (описание), сохраняем в description
    if "Опиши этот чертеж" in question or "техническое описание" in question:
        update_data["description"] = answer

    drawings_collection.update_one({"id": drawing_id}, {"$set": update_data})

    return {"status": status, "drawing_id": drawing_id}