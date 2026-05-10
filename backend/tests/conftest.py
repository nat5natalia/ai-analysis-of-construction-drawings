import pytest
from httpx import AsyncClient, ASGITransport
from main import app
from db import db_manager
import os

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.fixture(autouse=True)
async def clean_storage():
    """Очистка коллекции MongoDB перед каждым тестом"""
    await db_manager.connect()
    await db_manager.collection.delete_many({})
    
    # Очистка папки uploads
    upload_dir = os.getenv("DATASET_PATH", "uploads")
    if os.path.exists(upload_dir):
        for f in os.listdir(upload_dir):
            try:
                os.remove(os.path.join(upload_dir, f))
            except Exception:
                pass
    yield