import pytest
import numpy as np
import shutil
import os
from rag.vectors import VectorDB


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "vdb_test")


def test_persistence(db_path):
    # 1. Создаем БД и добавляем данные
    db = VectorDB(dimension=4, save_dir=db_path)
    vec = np.array([[1, 0, 0, 0]], dtype='float32')
    db.add(vec, [100], [{"info": "test"}])
    assert db.count() == 1

    # 2. Удаляем объект из памяти (имитируем перезагрузку)
    del db

    # 3. Создаем новый объект по тому же пути
    new_db = VectorDB(dimension=4, save_dir=db_path)
    assert new_db.count() == 1

    # 4. Проверяем поиск
    res = new_db.search(np.array([1, 0, 0, 0]), k=1)
    assert res[0]['id'] == 100
    assert res[0]['metadata']['info'] == "test"