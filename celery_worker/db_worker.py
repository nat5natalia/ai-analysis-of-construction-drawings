# db_worker.py
from pymongo import MongoClient
import os
import time


def get_drawing_sync(drawing_id):
    client = MongoClient(os.getenv("MONGO_URL", "mongodb://mongodb:27017"))
    try:
        db = client["drawings_db"]
        drawings = db["drawings"]

        # Пробуем найти 3 раза с небольшой паузой
        for _ in range(3):
            res = drawings.find_one({"id": drawing_id})
            if res:
                return res
            time.sleep(0.5)
        return None
    finally:
        client.close()