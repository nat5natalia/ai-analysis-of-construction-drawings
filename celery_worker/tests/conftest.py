import pytest
from unittest.mock import patch, MagicMock
from worker import app as celery_app

# ==================== КОНФИГУРАЦИЯ CELERY ====================

@pytest.fixture
def celery_config():
    """Настройки Celery для тестов (in-memory брокер)"""
    return {
        "broker_url": "memory://",
        "result_backend": "memory://",
        "task_always_eager": True,      # задачи выполняются синхронно
        "task_eager_propagates": True,
    }

@pytest.fixture
def celery_app():
    return celery_app


# ==================== МОКИ ДЛЯ ВНЕШНИХ ЗАВИСИМОСТЕЙ ====================

@pytest.fixture
def mock_mongo():
    """Мок MongoDB"""
    with patch("worker.MongoClient") as mock:
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        
        mock.return_value = mock_client
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        
        yield mock_collection

@pytest.fixture
def mock_redis():
    """Мок Redis"""
    with patch("worker.redis.from_url") as mock:
        mock_client = MagicMock()
        mock.return_value = mock_client
        yield mock_client

@pytest.fixture
def mock_vector_db():
    """Мок векторной БД (FAISS)"""
    with patch("worker.vector_db") as mock:
        yield mock

@pytest.fixture
def mock_embedding():
    """Мок функции compute_embedding"""
    with patch("worker.compute_embedding") as mock:
        mock.return_value = [0.1, 0.2, 0.3]
        yield mock

@pytest.fixture
def mock_requests():
    """Мок библиотеки requests"""
    with patch("worker.requests") as mock:
        yield mock

@pytest.fixture
def mock_get_drawing():
    """Мок функции get_drawing_sync"""
    with patch("worker.get_drawing_sync") as mock:
        yield mock