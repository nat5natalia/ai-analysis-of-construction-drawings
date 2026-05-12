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

# Инициализация Celery и Redis клиента для уведомлений
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
    """Отправка уведомления в Redis Pub/Sub для вебсокетов бэкенда"""
    message = {
        "drawing_id": drawing_id,
        "status": status,
        "answer": answer,
        "error": error,
        "event": "analysis_finished" if status == "completed" else "status_update"
    }
    try:
        redis_client.publish("drawing_updates", json.dumps(message))
    except Exception as e:
        logger.error(f"Ошибка публикации в Redis: {e}")


@app.task(name="process_drawing", bind=True, max_retries=3)
def process_drawing(self, drawing_id: str, question: str):
    logger.info(f"[START] Обработка чертежа: {drawing_id}")
    current_time = datetime.now(timezone.utc).isoformat()

    # 1. Получение данных чертежа из БД
    drawing = get_drawing_sync(drawing_id)
    if not drawing:
        logger.error(f"Чертеж {drawing_id} не найден.")
        return {"status": "error"}

    # Проверяем, является ли это самым первым анализом (описанием)
    is_initial_run = not bool(drawing.get("description"))

    # 2. Предварительное обновление статуса
    client = MongoClient(MONGO_URL)
    try:
        db = client[MONGO_DB]
        update_payload = {"status": "processing", "updated_at": current_time}

        # Если это НЕ первый запуск (чат), записываем вопрос пользователя в messages
        if not is_initial_run:
            db["drawings"].update_one(
                {"id": drawing_id},
                {
                    "$set": update_payload,
                    "$push": {"messages": {"role": "user", "content": question, "ts": current_time}}
                }
            )
        else:
            # Если это ПЕРВЫЙ запуск (техническое описание), в messages ничего не пишем
            db["drawings"].update_one({"id": drawing_id}, {"$set": update_payload})
    except Exception as e:
        logger.error(f"Ошибка БД (статус): {e}")
    finally:
        client.close()

    # 3. Запрос к ИИ-агенту
    file_path = drawing.get("file_path")
    page = drawing.get("page", 0)
    answer = None
    error_msg = None

    try:
        if not wait_for_agent():
            error_msg = "Таймаут агента"
        else:
            if is_initial_run:
                requests.post(f"{AGENT_BASE_URL}/pre-analyze",
                              json={"path": file_path, "page": page}, timeout=600).raise_for_status()

            resp = requests.post(f"{AGENT_BASE_URL}/process", json={
                "path": file_path,
                "question": question,
                "thread_id": drawing_id,
                "page": page
            }, timeout=120)
            resp.raise_for_status()

            result = resp.json()
            if result.get("success"):
                answer = result.get("answer")
            else:
                error_msg = result.get("error", "Ошибка агента")
    except Exception as e:
        error_msg = str(e)

    # 4. Финальное сохранение результатов
    client = MongoClient(MONGO_URL)
    try:
        db = client[MONGO_DB]
        finish_time = datetime.now(timezone.utc).isoformat()

        update_fields = {
            "status": "completed",
            "error": error_msg,
            "last_answer": answer,
            "updated_at": finish_time
        }
        update_op = {"$set": update_fields}

        if answer:
            if is_initial_run:
                # ЗАПИСЫВАЕМ ТОЛЬКО В description (в историю диалога не попадает)
                update_fields["description"] = answer
            else:
                # Добавляем ответ ассистента в историю диалога
                update_op["$push"] = {
                    "messages": {"role": "assistant", "content": answer, "ts": finish_time}
                }

        db["drawings"].update_one({"id": drawing_id}, update_op)
    finally:
        client.close()

    # 5. Сообщение в WebSocket
    notify_update(drawing_id, "completed", answer=answer, error=error_msg)
    return {"status": "completed"}