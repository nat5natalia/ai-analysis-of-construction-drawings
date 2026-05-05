import pytest
from unittest.mock import patch, MagicMock
from db import drawings

pytestmark = pytest.mark.asyncio


# Тест успешной загрузки чертежа
@patch("celery_worker.worker.process_drawing.delay")
async def test_upload_drawing_success(mock_celery, client):
    # Создаем фейковый PDF
    pdf_content = b"%PDF-1.4 test content"
    files = {"file": ("drawing.pdf", pdf_content, "application/pdf")}

    response = await client.post("/api/upload", files=files)

    # Проверяем ответ API
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processing"
    assert "id" in data

    # Проверяем, что задача ушла в Celery
    mock_celery.assert_called_once()

    # Проверяем, что запись появилась в MongoDB
    db_item = await drawings.find_one({"id": data["id"]})
    assert db_item is not None
    assert db_item["filename"] == "drawing.pdf"


# Тест ошибки при загрузке неверного формата
async def test_upload_wrong_format(client):
    files = {"file": ("test.txt", b"hello", "text/plain")}
    response = await client.post("/api/upload", files=files)
    assert response.status_code == 400
    assert "Неподдерживаемый формат" in response.json()["detail"]


# Тест удаления чертежа
async def test_delete_drawing(client):
    # Вручную добавляем запись для удаления
    d_id = "test-uuid"
    f_path = "uploads/test.pdf"
    with open(f_path, "w") as f: f.write("dummy")

    await drawings.insert_one({"id": d_id, "file_path": f_path})

    response = await client.delete(f"/api/drawings/{d_id}")
    assert response.status_code == 200

    # Проверяем, что в базе и на диске пусто
    assert await drawings.count_documents({"id": d_id}) == 0
    assert not os.path.exists(f_path)


# Тест прокси-поиска (имитируем ответ от Агента)
async def test_search_proxy(client):
    with patch("httpx.AsyncClient.post") as mock_post:
        # Имитируем успешный ответ от drawing-agent
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"total": 1, "results": [{"id": "1", "score": 0.95}]}
        )

        response = await client.get("/api/search", params={"q": "фундамент"})
        assert response.status_code == 200
        assert response.json()["total"] == 1