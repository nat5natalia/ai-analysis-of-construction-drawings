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


def wait_for_agent(timeout_minutes=15):
    """Ожидание готовности ИИ-агента к работе"""
    start_time = time.time()
    ready_url = f"{AGENT_BASE_URL}/ready"

    while time.time() - start_time < timeout_minutes * 60:
        try:
            response = requests.get(ready_url, timeout=5)
            if response.status_code == 200 and response.json().get("status") == "ready":
                return True
            logger.info("Агент инициализируется. Повторная проверка через 10 секунд...")
        except Exception as e:
            logger.error(f"Агент недоступен: {e}")
        time.sleep(10)
    return False


def notify_update(drawing_id: str, status: str, answer: str = None):
    """Уведомление фронтенда через Redis Pub/Sub"""
    message = {
        "drawing_id": drawing_id,
        "status": status,
        "event": "update",
        "answer": answer  # Передаем ответ; main.py упакует его в IMessage.text
    }

    if answer:
        logger.info(f"Отправка ответа в Redis для {drawing_id}: {answer[:50]}...")

    try:
        redis_client.publish("drawing_updates", json.dumps(message))
    except Exception as e:
        logger.error(f"Ошибка публикации в Redis: {e}")


@app.task(name="process_drawing", bind=True, max_retries=3)
def process_drawing(self, drawing_id: str, question: str):
    logger.info(f"[START] Обработка чертежа: {drawing_id}")

    drawing = get_drawing_sync(drawing_id)
    if not drawing:
        logger.error(f"Чертеж {drawing_id} не найден.")
        return {"status": "failed", "message": "Drawing not found"}

    is_initial_run = not bool(drawing.get("description"))
    client = MongoClient(MONGO_URL)
    db = client[MONGO_DB]

    try:
        current_time = datetime.now(timezone.utc).isoformat()

        # 1. Сохранение вопроса пользователя (если это не первичный промпт)
        if not is_initial_run:
            db["drawings"].update_one(
                {"id": drawing_id},
                {
                    "$set": {"status": "processing", "updated_at": current_time},
                    "$push": {
                        "messages": {
                            "role": "user",
                            "text": question,      # Поле для отображения на фронте
                            "content": question,   # Поле для истории LLM
                            "ts": current_time
                        }
                    }
                }
            )
        else:
            db["drawings"].update_one(
                {"id": drawing_id},
                {"$set": {"status": "processing", "updated_at": current_time}}
            )

        notify_update(drawing_id, "processing")

        file_path = drawing.get("file_path")
        page = drawing.get("page", 0)
        answer = None
        error_msg = None

        # 2. Взаимодействие с ИИ-Агентом
        if not wait_for_agent():
            error_msg = "Таймаут: агент не ответил вовремя"
        else:
            try:
                if is_initial_run:
                    logger.info(f"Первичный анализ: {file_path}")
                    requests.post(
                        f"{AGENT_BASE_URL}/pre-analyze",
                        json={"path": file_path, "page": page},
                        timeout=600
                    ).raise_for_status()

                resp = requests.post(f"{AGENT_BASE_URL}/process", json={
                    "path": file_path,
                    "question": question,
                    "thread_id": drawing_id,
                    "page": page
                }, timeout=180)
                resp.raise_for_status()

                result = resp.json()
                if result.get("success"):
                    answer = result.get("answer")
                else:
                    error_msg = result.get("error", "Неизвестная ошибка агента")
            except Exception as e:
                logger.error(f"Ошибка запроса к агенту: {e}")
                error_msg = f"Ошибка связи с ИИ: {str(e)}"

        # 3. Подготовка финального обновления
        finish_time = datetime.now(timezone.utc).isoformat()
        final_status = "completed" if not error_msg else "failed"

        update_set = {
            "status": final_status,
            "error": error_msg,
            "updated_at": finish_time,
            "last_answer": answer
        }

        update_op = {"$set": update_set}

        if answer:
            if is_initial_run:
                # Для первичного запуска записываем результат в описание
                update_set["description"] = answer
            else:
                # Для диалога пушим в историю с корректными полями IMessage
                update_op["$push"] = {
                    "messages": {
                        "role": "assistant",
                        "text": answer,     # Основной текст для фронтенда
                        "content": answer,
                        "ts": finish_time
                    }
                }

        # Финальное сохранение в MongoDB
        db["drawings"].update_one({"id": drawing_id}, update_op)

        # Уведомляем бэкенд (main.py), который перешлет это в WebSocket
        notify_update(drawing_id, final_status, answer=answer)

    except Exception as e:
        logger.error(f"Критическая ошибка воркера: {e}")
        db["drawings"].update_one(
            {"id": drawing_id},
            {"$set": {"status": "failed", "error": str(e)}}
        )
        raise self.retry(exc=e, countdown=10)
    finally:
        client.close()

    return {"status": "completed"}