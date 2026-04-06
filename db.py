from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "drawings_db"

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

drawings = db["drawings"]

async def save_drawing(drawing: dict):
    print(">>> СОХРАНЯЕМ В MONGO:", drawing["id"])
    result = await drawings.insert_one(drawing)
    print(">>> СОХРАНЕНО, _id:", result.inserted_id)

async def get_drawing(drawing_id: str):
    return await drawings.find_one({"id": drawing_id})

async def update_drawing(drawing_id: str, fields: dict):
    await drawings.update_one(
        {"id": drawing_id},
        {"$set": fields}
    )

async def get_all_with_embeddings():
    cursor = drawings.find({"embedding": {"$exists": True}})
    return await cursor.to_list(length=1000)

async def get_all_drawings():
    cursor = drawings.find({})
    return await cursor.to_list(length=1000)

async def delete_drawing(drawing_id: str):
    await drawings.delete_one({"id": drawing_id})