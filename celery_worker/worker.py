import os
import requests
import logging
import time
import sys
from datetime import datetime, timezone

# Гарантируем, что воркер видит соседние модули
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from celery import Celery
from db_worker import get_drawing_sync, MongoClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
# Берем базовый URL. Если в env придет со слешем или без — обработаем ниже.
AGENT_BASE_URL = os.getenv("AGENT_URL", "http://drawing_agent:8000").rstrip('/')

app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)


@app.task(name="process_drawing", bind=True, max_retries=3)
def process_drawing(self, drawing_id: str, question: str):
    logger.info(f"--- [Запуск] Чертеж: {drawing_id} | Вопрос: {question} ---")

    # 1. Ждем появления чертежа в БД
    drawing = None
    for attempt in range(5):
        drawing = get_drawing_sync(drawing_id)
        if drawing:
            break
        logger.info(f"Попытка {attempt + 1}: ожидание записи {drawing_id} в БД...")
        time.sleep(2)

    if not drawing:
        logger.error(f"Чертеж {drawing_id} не найден.")
        return {"status": "failed", "error": "Drawing not found in DB"}

    # 2. Формируем запрос
    # Если в AGENT_URL в докере уже был '/process', убираем его, чтобы добавить чисто
    clean_url = AGENT_BASE_URL.replace('/process', '')
    target_url = f"{clean_url}/process"

    payload = {
        "path": drawing.get("file_path"),
        "question": question,
        "thread_id": drawing_id,
        "page": drawing.get("page", 0)  # Добавили поле page
    }

    try:
        logger.info(f"Отправка на: {target_url}")
        # Таймаут 10 минут (600 сек) для тяжелого анализа
        response = requests.post(target_url, json=payload, timeout=600)

        if response.status_code == 404:
            logger.error(f"Эндпоинт {target_url} не найден (404)!")
            return {"status": "failed", "error": "Agent endpoint not found"}

        response.raise_for_status()
        result = response.json()

        if result.get("success"):
            status = "completed"
            answer = result.get("answer")
            error_msg = None
        else:
            status = "failed"
            answer = None
            error_msg = result.get("error", "Unknown agent error")

    except requests.exceptions.HTTPError as http_err:
        # Ретрай при временных ошибках сети/агента
        if response.status_code in (502, 503, 504):
            logger.warning(f"Ошибка {response.status_code}, пробую еще раз...")
            raise self.retry(exc=http_err, countdown=30)
        status = "failed"
        error_msg = f"HTTP {response.status_code}: {response.text}"
        answer = None
    except Exception as e:
        logger.error(f"Ошибка связи: {e}")
        status = "failed"
        error_msg = str(e)
        answer = None

    # 3. Обновление БД
    client = MongoClient(os.getenv("MONGO_URL", "mongodb://mongodb:27017"))
    try:
        db = client[os.getenv("MONGO_DB", "drawings_db")]

        # Используем isoformat для дат
        current_time = datetime.now(timezone.utc).isoformat()

        update_data = {
            "status": status,
            "error": error_msg,
            "last_answer": answer,
            "updated_at": current_time
        }

        # Если вопрос был про описание, сохраняем в поле description
        is_description = any(k in question.lower() for k in ["опиши", "описание"])
        if answer and is_description:
            update_data["description"] = answer

        db["drawings"].update_one({"id": drawing_id}, {"$set": update_data})
    finally:
        client.close()

    logger.info(f"--- [Завершено] {drawing_id} | Статус: {status} ---")
    return {"status": status}