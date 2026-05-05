import pytest
from unittest.mock import MagicMock
from app.drawing_cache import DrawingKnowledgeManager


@pytest.fixture
def mock_vdb():
    return MagicMock()


@pytest.fixture
def manager(mock_vdb, tmp_path):
    return DrawingKnowledgeManager(vector_db=mock_vdb, cache_dir=str(tmp_path))


def test_drawing_hash(manager):
    h1 = manager._get_drawing_hash("path/to/1.pdf", 0)
    h2 = manager._get_drawing_hash("path/to/1.pdf", 0)
    h3 = manager._get_drawing_hash("path/to/2.pdf", 0)

    assert h1 == h2
    assert h1 != h3


def test_retrieve_context_filtering(manager, mock_vdb):
    # Имитируем поиск в FAISS
    hash_id = manager._get_drawing_hash("test.pdf", 0)
    mock_vdb.search.return_value = [
        {"metadata": {"text": "Нашел меня", "drawing_hash": hash_id}},
        {"metadata": {"text": "Чужой чертеж", "drawing_hash": "other_hash"}}
    ]

    context = manager.retrieve_context("test.pdf", 0, "какой-то вопрос")
    assert "Нашел меня" in context
    assert "Чужой чертеж" not in context
    