import os
import requests
import logging
import time
import sys
import json
import redis
from datetime import datetime, timezone

# Обеспечение корректного импорта локальных модулей
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from celery import Celery
from db_worker import get_drawing_sync, MongoClient

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# --- Параметры окружения ---
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongodb:27017")
MONGO_DB = os.getenv("MONGO_DB", "drawings_db")
AGENT_BASE_URL = os.getenv("AGENT_URL", "http://drawing_agent:8000").rstrip('/')

# --- Инициализация Celery и Redis ---
app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)
redis_client = redis.from_url(REDIS_URL)


def wait_for_agent(timeout_minutes=5):
    """
    Ожидание готовности ИИ-агента.
    Таймаут сокращен, чтобы не блокировать очередь Celery слишком долго.
    """
    start_time = time.time()
    ready_url = f"{AGENT_BASE_URL}/ready"

    while time.time() - start_time < timeout_minutes * 60:
        try:
            response = requests.get(ready_url, timeout=5)
            if response.status_code == 200 and response.json().get("status") == "ready":
                return True
            logger.info("Агент инициализируется или занят. Повтор через 10 сек...")
        except Exception as e:
            logger.error(f"Агент недоступен по {ready_url}: {e}")
        time.sleep(10)
    return False


def notify_update(drawing_id: str, status: str, answer: str = None):
    """Уведомление фронтенда через Redis Pub/Sub."""
    event_type = "new_message" if answer else "update"

    message = {
        "drawing_id": str(drawing_id),
        "status": status,
        "event": event_type
    }

    if answer:
        # В объекте уведомления пробрасываем ответ для мгновенного отображения
        message["answer"] = answer

    try:
        redis_client.publish("drawing_updates", json.dumps(message))
        logger.info(f"Published to Redis: ID={drawing_id}, Event={event_type}")
    except Exception as e:
        logger.error(f"Ошибка публикации в Redis: {e}")


@app.task(name="process_drawing", bind=True, max_retries=3)
def process_drawing(self, drawing_id: str, question: str):
    logger.info(f"[START] Обработка чертежа: {drawing_id}")

    drawing = get_drawing_sync(drawing_id)
    if not drawing:
        logger.error(f"Чертеж {drawing_id} не найден.")
        return {"status": "failed", "message": "Drawing not found"}

    # Если описания еще нет — это первичная индексация документа
    is_initial_run = not bool(drawing.get("description"))
    client = MongoClient(MONGO_URL)
    db = client[MONGO_DB]

    try:
        current_time = datetime.now(timezone.utc).isoformat()

        # 1. Обновляем статус в БД
        db["drawings"].update_one(
            {"id": drawing_id},
            {"$set": {"status": "processing", "updated_at": current_time}}
        )
        notify_update(drawing_id, "processing")

        file_path = drawing.get("file_path")
        page = drawing.get("page", 0)
        answer = None
        error_msg = None

        # 2. Проверка доступности ИИ-Агента
        if not wait_for_agent():
            error_msg = "Таймаут: ИИ-агент не ответил в отведенное время"
        else:
            try:
                # ВАЖНО: Всегда передаем drawing_id (UUID), чтобы агент не создавал дубликаты по хешам путей

                if is_initial_run:
                    logger.info(f"Запуск пре-анализа для {drawing_id}...")
                    requests.post(
                        f"{AGENT_BASE_URL}/pre-analyze",
                        json={
                            "path": file_path,
                            "drawing_id": drawing_id,
                            "page": page
                        },
                        timeout=600
                    ).raise_for_status()

                # Запрос на генерацию ответа
                resp = requests.post(f"{AGENT_BASE_URL}/process", json={
                    "path": file_path,
                    "drawing_id": drawing_id,
                    "question": question,
                    "thread_id": drawing_id,
                    "page": page
                }, timeout=300)
                resp.raise_for_status()

                result = resp.json()
                if result.get("success"):
                    answer = result.get("answer")
                else:
                    error_msg = result.get("error", "Агент вернул ошибку без описания")
            except Exception as e:
                error_msg = f"Ошибка связи с ИИ-агентом: {str(e)}"

        # 3. Финализация и сохранение результатов
        finish_time = datetime.now(timezone.utc).isoformat()
        final_status = "completed" if not error_msg else "failed"

        update_data = {
            "$set": {
                "status": final_status,
                "error": error_msg,
                "updated_at": finish_time
            }
        }

        if answer:
            if is_initial_run:
                # В БАЗУ сохраняем ТОЛЬКО в description
                logger.info(f"Saving initial description for {drawing_id}")
                update_data["$set"]["description"] = answer
            else:
                # В БАЗУ сохраняем ТОЛЬКО в массив сообщений
                logger.info(f"Adding new message to history for {drawing_id}")
                update_data["$push"] = {
                    "messages": {
                        "role": "assistant",
                        "text": answer,
                        "content": answer,
                        "ts": finish_time
                    }
                }

        # Выполняем сохранение в MongoDB
        db["drawings"].update_one({"id": drawing_id}, update_data)
        notify_update(drawing_id, final_status, answer=answer)

    except Exception as e:
        logger.error(f"Критическая ошибка воркера: {e}")
        db["drawings"].update_one(
            {"id": drawing_id},
            {"$set": {"status": "failed", "error": str(e)}}
        )
        # Повтор задачи при временных сбоях (например, сеть)
        raise self.retry(exc=e, countdown=15)
    finally:
        client.close()

    return {"status": final_status}