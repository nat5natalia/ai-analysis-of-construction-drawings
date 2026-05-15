import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_agent():
    """Мок агента для API тестов"""
    with patch("main.agent_instance") as mock:
        mock.pre_analyze = AsyncMock(return_value={"success": True, "error": None})
        mock.run = AsyncMock(return_value={"success": True, "answer": "Test answer"})
        mock.vector_db = MagicMock()
        mock.vector_db.search = MagicMock(return_value=[])
        mock.drawing_knowledge = MagicMock()
        mock.drawing_knowledge.embed_model.generate = MagicMock(return_value=[0.1, 0.2, 0.3])
        mock.lock = MagicMock()
        mock.lock.locked.return_value = False
        mock._ensure_initialized = AsyncMock()
        yield mock


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_endpoint_when_ready():
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] in ["ready", "initializing"]


def test_pre_analyze_endpoint():
    response = client.post("/pre-analyze", json={
        "path": "/app/dataset/drawing.jpg",
        "drawing_id": "test-uuid-123",
        "page": 0
    })
    assert response.status_code == 200


def test_process_endpoint():
    response = client.post("/process", json={
        "path": "/app/dataset/drawing.jpg",
        "question": "Что на чертеже?",
        "page": 0
    })
    assert response.status_code == 200


def test_process_endpoint_returns_400_for_empty_question():
    response = client.post("/process", json={
        "path": "/app/dataset/drawing.jpg",
        "question": "",
        "page": 0
    })
    assert response.status_code == 400


def test_search_endpoint():
    response = client.post("/search", json={
        "query": "колонна",
        "limit": 5
    })
    assert response.status_code == 200
    assert "results" in response.json()