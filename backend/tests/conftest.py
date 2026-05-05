import pytest
import asyncio
import os
from httpx import AsyncClient, ASGITransport
from main import app
from db import drawings
from motor.motor_asyncio import AsyncIOMotorClient

# Настройка единого цикла событий для асинхронных тестов
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

# Фикстура для HTTP-клиента
@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

# Очистка базы и файлов перед каждым тестом
@pytest.fixture(autouse=True)
async def clean_storage():
    await drawings.delete_many({})
    upload_dir = os.getenv("DATASET_PATH", "uploads")
    if os.path.exists(upload_dir):
        for f in os.listdir(upload_dir):
            os.remove(os.path.join(upload_dir, f))
    yield