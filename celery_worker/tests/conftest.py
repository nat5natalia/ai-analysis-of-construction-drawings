import pytest
from unittest.mock import patch, MagicMock
from worker import app as celery_app


@pytest.fixture
def celery_config():
    return {
        "broker_url": "memory://",
        "result_backend": "memory://",
        "task_always_eager": True,
        "task_eager_propagates": True,
    }


@pytest.fixture
def celery_app():
    return celery_app


@pytest.fixture
def mock_mongo():
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
    with patch("worker.redis.from_url") as mock:
        mock_client = MagicMock()
        mock.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_requests():
    with patch("worker.requests") as mock:
        yield mock


@pytest.fixture
def mock_get_drawing():
    with patch("worker.get_drawing_sync") as mock:
        yield mock
