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

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# Параметры окружения
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongodb:27017")
MONGO_DB = os.getenv("MONGO_DB", "drawings_db")
AGENT_BASE_URL = os.getenv("AGENT_URL", "http://drawing_agent:8000").rstrip('/')

# Инициализация Celery и Redis
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


def notify_update(drawing_id: str, status: str, answer: str = None, error: str = None):
    """Отправка уведомления в Redis Pub/Sub для вебсокетов"""
    message = {
        "drawing_id": drawing_id,
        "status": status,
        "answer": answer,
        "error": error,
        "event": "status_update" if status == "processing" else "analysis_finished"
    }
    try:
        redis_client.publish("drawing_updates", json.dumps(message))
    except Exception as e:
        logger.error(f"Ошибка публикации в Redis: {e}")


@app.task(name="process_drawing", bind=True, max_retries=3)
def process_drawing(self, drawing_id: str, question: str):
    logger.info(f"[START] Обработка чертежа: {drawing_id}")

    # 1. Получение данных чертежа
    drawing = get_drawing_sync(drawing_id)
    if not drawing:
        logger.error(f"Чертеж {drawing_id} не найден.")
        return {"status": "error", "message": "Drawing not found"}

    # Проверяем, первичный ли это анализ (описание)
    is_initial_run = not bool(drawing.get("description"))

    # Открываем соединение с БД один раз на всю задачу
    client = MongoClient(MONGO_URL)
    db = client[MONGO_DB]

    try:
        # 2. Обновляем только статус (вопрос уже сохранен в бэкенде)
        current_time = datetime.now(timezone.utc).isoformat()
        db["drawings"].update_one(
            {"id": drawing_id},
            {"$set": {"status": "processing", "updated_at": current_time}}
        )
        # Уведомляем фронтенд, что начали думать
        notify_update(drawing_id, "processing")

        # 3. Работа с ИИ-агентом
        file_path = drawing.get("file_path")
        page = drawing.get("page", 0)
        answer = None
        error_msg = None

        if not wait_for_agent():
            error_msg = "Таймаут: агент не ответил вовремя"
        else:
            try:
                # Если первый запуск — просим агента проанализировать файл
                if is_initial_run:
                    requests.post(f"{AGENT_BASE_URL}/pre-analyze",
                                  json={"path": file_path, "page": page},
                                  timeout=600).raise_for_status()

                # Основной запрос
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

        # 4. Финальное сохранение результатов
        finish_time = datetime.now(timezone.utc).isoformat()
        update_fields = {
            "status": "completed" if not error_msg else "error",
            "error": error_msg,
            "last_answer": answer,
            "updated_at": finish_time
        }

        update_op = {"$set": update_fields}

        if answer:
            if is_initial_run:
                # Для первого раза пишем в description
                update_op["$set"]["description"] = answer
            else:
                # Для чата добавляем ответ ассистента в историю
                update_op["$push"] = {
                    "messages": {"role": "assistant", "content": answer, "ts": finish_time}
                }

        db["drawings"].update_one({"id": drawing_id}, update_op)

        # 5. Публикация результата в WebSocket
        notify_update(drawing_id, "completed" if not error_msg else "error", answer=answer, error=error_msg)

    except Exception as e:
        logger.error(f"Критическая ошибка воркера: {e}")
        # В случае падения — пытаемся пометить чертеж как ошибочный в БД
        db["drawings"].update_one({"id": drawing_id}, {"$set": {"status": "error", "error": str(e)}})
        raise self.retry(exc=e, countdown=10)  # Перезапуск задачи при сбое
    finally:
        client.close()

    return {"status": "completed"}