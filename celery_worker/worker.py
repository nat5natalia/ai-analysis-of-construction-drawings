import os
import requests
import logging
import time
import sys
from datetime import datetime, timezone
import redis
import json

from vector_db import vector_db
from ds import compute_embedding 

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
        logger.info("Checking agent availability...")
        
        if not wait_for_agent():
            logger.error("Проблема с агентом: таймаут ожидания готовности.")
            error_msg = "Agent timeout"
        else:
            if is_initial_run:
                requests.post(f"{AGENT_BASE_URL}/pre-analyze",
                              json={"path": file_path, "page": page}, timeout=600).raise_for_status()
                logger.info("Agent pre-analyze completed")   # <-- добавить

            resp = requests.post(f"{AGENT_BASE_URL}/process", json={
                "path": file_path,
                "question": question,
                "thread_id": drawing_id,
                "page": page
            }, timeout=120)
            resp.raise_for_status()
            logger.info("Agent process completed")          # <-- добавить
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
            # Добавляем ответ в историю сообщений
            update_op["$push"] = {"messages": {"role": "assistant", "content": answer, "ts": finish_time}}

            # Вычисляем эмбеддинг и сохраняем в FAISS и БД
            logger.info("Computing embedding...")
            embedding = compute_embedding(answer)
            # embedding = compute_embedding(answer)   # дубликат удалён
            try:
                vector_db.add(drawing_id, embedding)
                update_fields["embedding"] = embedding
                logger.info(f"Embedding saved for {drawing_id}")   # <-- лог успеха
            except Exception as e:
                logger.error(f"FAISS add error: {e}")

        # Применяем обновление в БД
        db["drawings"].update_one({"id": drawing_id}, update_op)

        # Публикуем событие в Redis
        logger.info("Publishing status update to Redis...")   # <-- лог перед публикацией
        try:
            r = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
            # Чтобы получить актуальный список сообщений, можно перечитать документ
            updated_doc = db["drawings"].find_one({"id": drawing_id}, {"messages": 1})
            current_messages = updated_doc.get("messages", []) if updated_doc else []
            event = {
                "type": "status_update",
                "status": "completed",
                "messages": current_messages,
                "last_answer": answer,
                "error": error_msg
            }
            r.publish(f"drawing_updates:{drawing_id}", json.dumps(event, default=str))
            logger.info("Published to Redis channel")   # <-- лог успеха публикации
        except Exception as e:
            logger.error(f"Redis publish error: {e}")

    finally:
        client.close()

    return {"status": "completed"}