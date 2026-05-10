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
AGENT_BASE_URL = os.getenv("AGENT_URL", "http://drawing_agent:8000").rstrip('/')

app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)


def wait_for_agent(timeout_minutes=15):
    start_time = time.time()
    ready_url = f"{AGENT_BASE_URL}/ready"
    while time.time() - start_time < timeout_minutes * 60:
        try:
            response = requests.get(ready_url, timeout=5)
            if response.status_code == 200 and response.json().get("status") == "ready":
                return True
            logger.info("Агент занят или инициализируется. Ожидание 10 секунд...")
        except Exception as e:
            logger.error(f"Агент недоступен: {e}")
        time.sleep(10)
    return False


@app.task(name="process_drawing", bind=True, max_retries=3)
def process_drawing(self, drawing_id: str, question: str):
    logger.info(f"--- [Старт] Чертеж: {drawing_id} ---")
    current_time = datetime.now(timezone.utc).isoformat()

    drawing = get_drawing_sync(drawing_id)
    if not drawing:
        logger.error(f"Чертеж {drawing_id} не найден.")
        return {"status": "completed", "error": "Drawing not found"}

    has_description = bool(drawing.get("description"))
    is_initial_run = not has_description

    client = MongoClient(os.getenv("MONGO_URL", "mongodb://mongodb:27017"))
    try:
        db = client[os.getenv("MONGO_DB", "drawings_db")]
        update_payload = {"status": "processing", "updated_at": current_time}

        if not is_initial_run:
            db["drawings"].update_one(
                {"id": drawing_id},
                {
                    "$set": update_payload,
                    "$push": {"messages": {"role": "user", "content": question, "ts": current_time}}
                }
            )
        else:
            db["drawings"].update_one({"id": drawing_id}, {"$set": update_payload})
    except Exception as e:
        logger.error(f"Ошибка предварительного сохранения: {e}")
    finally:
        client.close()

    file_path = drawing.get("file_path")
    page = drawing.get("page", 0)

    answer = None
    error_msg = None

    try:
        if not wait_for_agent():
            logger.error("Проблема с агентом: таймаут ожидания готовности.")
            error_msg = "Agent timeout"
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
                logger.error(f"Проблема с агентом: {result.get('error', 'Unknown error')}")
                error_msg = result.get("error", "Unknown agent error")

    except Exception as e:
        logger.error(f"Проблема с агентом (Exception): {e}")
        error_msg = str(e)

    client = MongoClient(os.getenv("MONGO_URL", "mongodb://mongodb:27017"))
    try:
        db = client[os.getenv("MONGO_DB", "drawings_db")]
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
                update_fields["description"] = answer
            else:
                update_op["$push"] = {"messages": {"role": "assistant", "content": answer, "ts": finish_time}}

        db["drawings"].update_one({"id": drawing_id}, update_op)

    finally:
        client.close()

    return {"status": "completed"}