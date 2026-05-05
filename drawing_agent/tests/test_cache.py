import pytest
import os
import json
from app.cache import AgentCache


def test_cache_set_get():
    cache = AgentCache()
    cache.set("key1", {"data": "test"})
    assert cache.get("key1") == {"data": "test"}
    assert cache.get("unknown") is None


def test_cache_flush(tmp_path):
    # Подменяем рабочую директорию для логов
    os.chdir(tmp_path)
    cache = AgentCache()
    cache.set("session_1", {"answer": "hello"})
    cache.flush_to_log()

    log_files = list(tmp_path.glob("logs/cache_*.json"))
    assert len(log_files) == 1
    with open(log_files[0], 'r', encoding='utf-8') as f:
        data = json.load(f)
        assert data["session_1"]["answer"] == "hello"