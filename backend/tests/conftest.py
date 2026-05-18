import os

import pytest
from httpx import ASGITransport, AsyncClient

from db import db_manager
from main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
async def clean_storage():
    await db_manager.connect()
    await db_manager.collection.delete_many({})
    upload_dir = os.getenv("DATASET_PATH", "uploads")
    if os.path.exists(upload_dir):
        for filename in os.listdir(upload_dir):
            try:
                os.remove(os.path.join(upload_dir, filename))
            except Exception:
                pass
    yield
