from pymongo import MongoClient
import os

def get_drawing_sync(drawing_id):
    """Get drawing with per-call initialization for Celery fork safety"""
    client = MongoClient(os.getenv("MONGO_URL", "mongodb://mongodb:27017"))
    try:
        db = client["drawings_db"]
        drawings = db["drawings"]
        return drawings.find_one({"id": drawing_id})
    finally:
        client.close()