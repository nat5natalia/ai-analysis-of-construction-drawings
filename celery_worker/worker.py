import os
import requests
import logging
import time
from celery import Celery
from pymongo import MongoClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongodb:27017")
DB_NAME = os.getenv("MONGO_DB", "drawings_db")
AGENT_URL = os.getenv("AGENT_URL", "http://drawing-agent:8000/process")

app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)


@app.task(name="process_drawing", bind=True, max_retries=3)
def process_drawing(self, drawing_id: str, question: str):
    logger.info(f"--- [Запуск] Чертеж: {drawing_id} | Вопрос: {question} ---")

    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    drawings_collection = db["drawings"]

    # 1. Поиск чертежа в БД
    drawing = None
    for attempt in range(5):
        drawing = drawings_collection.find_one({"id": drawing_id})
        if drawing:
            break
        logger.info(f"Попытка {attempt + 1}: чертеж {drawing_id} еще не в БД, ждем...")
        time.sleep(2)

    if not drawing:
        logger.error(f"Чертеж {drawing_id} не найден после 5 попыток.")
        client.close()
        return {"status": "failed", "error": "Drawing not found in DB"}

    # 2. Подготовка запроса к агенту
    # Берем путь из БД. Важно, чтобы этот путь был доступен внутри контейнера агента!
    file_path = drawing.get("file_path")
    payload = {
        "path": file_path,
        "question": question,
        "thread_id": drawing_id
    }

    try:
        logger.info(f"Отправка запроса к Агенту: {AGENT_URL}")
        # Таймаут 600 секунд (10 минут) — критично для тяжелых нейросетей
        response = requests.post(AGENT_URL, json=payload, timeout=600)

        # Логируем сырой ответ для отладки
        logger.info(f"Ответ Агента (код {response.status_code}): {response.text}")

        response.raise_for_status()
        result = response.json()

        if result.get("success") or "answer" in result:
            status = "completed"
            answer = result.get("answer")
            # Если агент сохранил новую картинку (с разметкой), он должен вернуть 'processed_path'
            processed_path = result.get("processed_path")
            error_msg = None
        else:
            status = "failed"
            answer = None
            processed_path = None
            error_msg = result.get("error", "Unknown agent error")

    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        logger.warning(f"Агент недоступен или занят, ретрай через 30 сек... Ошибка: {exc}")
        client.close()
        raise self.retry(exc=exc, countdown=30)
    except Exception as e:
        logger.error(f"Критическая ошибка при связи с агентом: {e}")
        status = "failed"
        answer = None
        processed_path = None
        error_msg = str(e)

    # 3. Обновление данных в MongoDB
    update_data = {
        "status": status,
        "error": error_msg,
        "last_answer": answer,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
    }

    # Если получили описание — сохраняем его
    if answer and any(keyword in question.lower() for keyword in ["опиши", "описание", "техническое"]):
        update_data["description"] = answer

    # ВАЖНО: Если агент вернул путь к обработанному изображению, обновляем его,
    # чтобы фронтенд загрузил новую версию картинки.
    if processed_path:
        logger.info(f"Обновляем путь к файлу на обработанный: {processed_path}")
        update_data["file_path"] = processed_path

    drawings_collection.update_one({"id": drawing_id}, {"$set": update_data})

    client.close()
    logger.info(f"--- [Завершено] Статус: {status} для {drawing_id} ---")
    return {"status": status, "drawing_id": drawing_id}