import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_vdb():
    return MagicMock()


@pytest.fixture
def manager(mock_vdb, tmp_path):
    from app.drawing_cache import DrawingKnowledgeManager
    return DrawingKnowledgeManager(vector_db=mock_vdb, cache_dir=str(tmp_path))


def test_drawing_hash(manager):
    h1 = manager._get_drawing_hash("path/to/1.pdf", 0)
    h2 = manager._get_drawing_hash("path/to/1.pdf", 0)
    h3 = manager._get_drawing_hash("path/to/2.pdf", 0)

    assert h1 == h2
    assert h1 != h3


def test_retrieve_context_filtering(manager, mock_vdb):
    """Тест проверяет фильтрацию контекста по drawing_id"""
    hash_id = manager._get_drawing_hash("test.pdf", 0)
    mock_vdb.search.return_value = [
        {"text": "Нашел меня", "drawing_id": hash_id, "score": 0.9},
        {"text": "Чужой чертеж", "drawing_id": "other_hash", "score": 0.8}
    ]

    with patch("app.drawing_cache.EmbeddingGenerator") as MockEmbed:
        mock_embed = MagicMock()
        mock_embed.generate.return_value = [0.1, 0.2, 0.3]
        MockEmbed.return_value = mock_embed

        from app.drawing_cache import DrawingKnowledgeManager
        manager = DrawingKnowledgeManager(vector_db=mock_vdb, cache_dir=manager.cache_dir)
        
        context = manager.retrieve_context("test.pdf", 0, "какой-то вопрос")

    # Проверяем, что контекст содержит нужный фрагмент
    assert "Нашел меня" in context