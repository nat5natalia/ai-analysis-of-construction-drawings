from pymongo import MongoClient
import os

client = MongoClient(os.getenv("MONGO_URL", "mongodb://mongodb:27017"))
db = client["drawings_db"]
drawings = db["drawings"]

def get_drawing_sync(drawing_id):
    return drawings.find_one({"id": drawing_id})