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
AGENT_BASE_URL = os.getenv("AGENT_URL", "http://drawing_agent:8000").rstrip('/')

app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)


@app.task(name="process_drawing", bind=True, max_retries=3)
def process_drawing(self, drawing_id: str, question: str):
    logger.info(f"--- [Запуск] Чертеж: {drawing_id} | Задача: {question} ---")

    drawing = None
    for attempt in range(5):
        drawing = get_drawing_sync(drawing_id)
        if drawing:
            break
        time.sleep(2)

    if not drawing:
        logger.error(f"Чертеж {drawing_id} не найден.")
        return {"status": "failed", "error": "Drawing not found in DB"}

    file_path = drawing.get("file_path")
    page = drawing.get("page", 0)
    has_description = bool(drawing.get("description"))
    try:
        if not has_description:
            logger.info(f"Первичный запуск. Выполняю pre-analyze для: {file_path}")
            pre_url = f"{AGENT_BASE_URL}/pre-analyze"
            pre_resp = requests.post(pre_url, json={"path": file_path, "page": page}, timeout=600)
            pre_resp.raise_for_status()
        else:
            logger.info(f"Чертеж {drawing_id} уже проанализирован, пропускаю pre-analyze.")

        target_url = f"{AGENT_BASE_URL}/process"
        payload = {
            "path": file_path,
            "question": question,
            "thread_id": drawing_id,
            "page": page
        }

        logger.info(f"Запрос анализа (process)...")
        response = requests.post(target_url, json=payload, timeout=600)
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

    except Exception as e:
        logger.error(f"Ошибка связи с агентом: {e}")
        status = "failed"
        error_msg = str(e)
        answer = None

    client = MongoClient(os.getenv("MONGO_URL", "mongodb://mongodb:27017"))
    try:
        db = client[os.getenv("MONGO_DB", "drawings_db")]
        current_time = datetime.now(timezone.utc).isoformat()

        messages_to_push = []
        messages_to_push.append({"role": "user", "content": question, "ts": current_time})
        if answer:
            messages_to_push.append({"role": "assistant", "content": answer, "ts": current_time})

        update_fields = {
            "status": status,
            "error": error_msg,
            "last_answer": answer,
            "updated_at": current_time
        }

        if answer and not drawing.get("description"):
            update_fields["description"] = answer

        db["drawings"].update_one(
            {"id": drawing_id},
            {
                "$set": update_fields,
                "$push": {"messages": {"$each": messages_to_push}}
            }
        )
    finally:
        client.close()

    logger.info(f"--- [Завершено] {drawing_id} | Статус: {status} ---")
    return {"status": status}