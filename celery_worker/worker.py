import os
import requests
import logging
import time
import sys
from datetime import datetime, timezone
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from celery import Celery
from db_worker import get_drawing_sync, MongoClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
# ВАЖНО: Убедитесь, что в docker-compose сервис называется drawing_agent
# И что URL не содержит лишних префиксов в конце
AGENT_URL = os.getenv("AGENT_URL", "http://drawing_agent:8000/process")

app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)


@app.task(name="process_drawing", bind=True, max_retries=3)
def process_drawing(self, drawing_id: str, question: str):
    logger.info(f"--- [Запуск] Чертеж: {drawing_id} | Вопрос: {question} ---")

    # 1. Поиск чертежа в БД через синхронный хелпер
    drawing = None
    for attempt in range(5):
        drawing = get_drawing_sync(drawing_id)
        if drawing:
            break
        logger.info(f"Попытка {attempt + 1}: чертеж {drawing_id} еще не в БД, ждем...")
        time.sleep(2)

    if not drawing:
        logger.error(f"Чертеж {drawing_id} не найден после 5 попыток.")
        return {"status": "failed", "error": "Drawing not found in DB"}

    # 2. Подготовка запроса к агенту
    file_path = drawing.get("file_path")
    payload = {
        "path": file_path,
        "question": question,
        "thread_id": drawing_id
    }

    try:
        # Очищаем URL от возможных двойных слешей при склейке, если это нужно
        target_url = AGENT_URL.rstrip('/')
        logger.info(f"Отправка запроса к Агенту: {target_url}")

        response = requests.post(target_url, json=payload, timeout=600)
        logger.info(f"Ответ Агента (код {response.status_code})")

        if response.status_code == 404:
            logger.error(f"Эндпоинт не найден! Проверьте AGENT_URL: {target_url}. Ответ: {response.text}")
            return {"status": "failed", "error": "Agent endpoint not found (404)"}

        response.raise_for_status()
        result = response.json()

        if result.get("success"):
            status = "completed"
            answer = result.get("answer")
            processed_path = result.get("processed_path")
            error_msg = None
        else:
            status = "failed"
            answer = None
            processed_path = None
            error_msg = result.get("error", "Unknown agent error")

    except requests.exceptions.HTTPError as http_err:
        if response.status_code in (502, 503, 504):
            raise self.retry(exc=http_err, countdown=30)
        status = "failed"
        error_msg = f"HTTP {response.status_code}: {response.text}"
        answer, processed_path = None, None
    except Exception as e:
        logger.error(f"Ошибка связи: {e}")
        status = "failed"
        error_msg = str(e)
        answer, processed_path = None, None

    # 3. Обновление в БД (используем прямое подключение для записи)
    client = MongoClient(os.getenv("MONGO_URL", "mongodb://mongodb:27017"))
    try:
        db = client[os.getenv("MONGO_DB", "drawings_db")]
        update_data = {
            "status": status,
            "error": error_msg,
            "last_answer": answer,
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        if answer and any(k in question.lower() for k in ["опиши", "описание"]):
            update_data["description"] = answer
        if processed_path:
            update_data["file_path"] = processed_path

        db["drawings"].update_one({"id": drawing_id}, {"$set": update_data})
    finally:
        client.close()

    logger.info(f"--- [Завершено] Статус: {status} ---")
    return {"status": status, "drawing_id": drawing_id}