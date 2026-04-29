"""
Celery Worker для асинхронной обработки запросов к Drawing Agent.

Этот модуль:
1. Слушает очередь задач в Redis.
2. Получает задачу (ID чертежа + вопрос пользователя).
3. Загружает чертёж из MongoDB.
4. Вызывает Drawing Agent (через HTTP).
5. Сохраняет результат обратно в MongoDB.
"""

import os
import json
from celery import Celery
from pymongo import MongoClient
import requests

# Подключение к Redis (брокер)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)

# Подключение к MongoDB
MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongodb:27017")
mongo_client = MongoClient(MONGO_URL)
db = mongo_client["construction_drawings"]
drawings_collection = db["drawings"]

# URL Drawing Agent 
AGENT_URL = os.getenv("AGENT_URL", "http://drawing-agent:8000/process")

@app.task(name="process_drawing")
def process_drawing(drawing_id: str, question: str):
    """Обработка запроса: достать чертёж, вызвать агента, сохранить результат"""
    
    # 1. Получение чертежа из MongoDB
    drawing = drawings_collection.find_one({"_id": drawing_id})
    if not drawing:
        return {"error": f"Drawing {drawing_id} not found"}
    
    # 2. Вызов Drawing Agent
    payload = {
        "image_base64": drawing.get("image_base64"),
        "question": question,
        "context": drawing.get("metadata", {})
    }
    
    try:
        response = requests.post(AGENT_URL, json=payload, timeout=120)
        result = response.json()
    except Exception as e:
        result = {"error": str(e)}
    
    # 3. Сохраненение результата в MongoDB
    drawings_collection.update_one(
        {"_id": drawing_id},
        {"$set": {"result": result, "status": "completed"}}
    )
    
    return result
