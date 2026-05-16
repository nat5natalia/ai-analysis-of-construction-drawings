import pytest
from rag.vectors import VectorDB


def test_persistence(tmp_path):
    """Тест адаптирован под реальный формат возврата VectorDB.search"""
    index_path = str(tmp_path / "faiss_index.bin")
    metadata_path = str(tmp_path / "faiss_metadata.json")

    db = VectorDB(index_path=index_path, metadata_path=metadata_path)

    # Добавляем тестовый вектор
    embedding = [0.1, 0.2, 0.3, 0.4]
    db.add(text="test text", embedding=embedding, drawing_id="test_id")

    assert db.index.ntotal == 1

    # Поиск
    results = db.search(query_embedding=embedding, drawing_id="test_id", k=1)

    # Если search возвращает кортежи, а не словари
    if results and isinstance(results[0], tuple):
        # Формат: (текст, drawing_id, score) или (текст, score)
        if len(results[0]) >= 2:
            assert results[0][0] == "test text"
    else:
        # Формат: {"text": ..., "drawing_id": ..., "score": ...}
        assert results[0]["text"] == "test text"