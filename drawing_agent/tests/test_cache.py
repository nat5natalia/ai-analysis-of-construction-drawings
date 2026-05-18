import pytest
from app.cache import AgentCache


def test_cache_set_and_get():
    """Проверка сохранения и получения из кэша"""
    cache = AgentCache(max_size=10, default_ttl=3600)
    key = ("thread1", "path/to/file.pdf", "Какие размеры?")
    value = {"success": True, "answer": "600x400"}

    cache.set(*key, value)
    result = cache.get(*key)

    assert result == value


def test_cache_ttl_expiration():
    """Проверка, что устаревшие записи не возвращаются"""
    cache = AgentCache(max_size=10, default_ttl=-1)  # Истекло сразу
    key = ("thread1", "path/to/file.pdf", "Вопрос")
    value = {"answer": "test"}

    cache.set(*key, value)
    result = cache.get(*key)

    assert result is None


def test_cache_max_size():
    """Проверка ограничения максимального размера"""
    cache = AgentCache(max_size=2, default_ttl=3600)

    cache.set("t1", "p1", "q1", "value1")
    cache.set("t2", "p2", "q2", "value2")
    cache.set("t3", "p3", "q3", "value3")

    assert cache.get("t1", "p1", "q1") is None
    assert cache.get("t2", "p2", "q2") == "value2"
    assert cache.get("t3", "p3", "q3") == "value3"