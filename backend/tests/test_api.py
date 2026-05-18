import pytest

from db import db_manager


pytestmark = pytest.mark.asyncio


async def test_health_check(client):
    """Проверка, что бэкенд вообще отвечает"""
    response = await client.get("/api/drawings")
    assert response.status_code == 200


async def test_upload_drawing_success(client):
    """Загрузка корректного PDF-файла"""
    pdf_content = b"%PDF-1.4 test content"
    files = {"file": ("drawing.pdf", pdf_content, "application/pdf")}

    response = await client.post("/api/upload", files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processing"
    assert "id" in data

    db_item = await db_manager.collection.find_one({"id": data["id"]})
    assert db_item is not None
    assert db_item["filename"] == "drawing.pdf"


async def test_get_drawing_not_found(client):
    """Запрос несуществующего чертежа"""
    response = await client.get("/api/drawings/nonexistent-id")
    assert response.status_code == 404


async def test_get_all_drawings_empty(client):
    """Список чертежей, когда база пуста"""
    response = await client.get("/api/drawings")
    assert response.status_code == 200
    data = response.json()
    assert "drawings" in data
    assert data["total"] == 0


async def test_delete_drawing(client):
    """Загрузка -> проверка -> удаление чертежа"""
    files = {"file": ("to_delete.pdf", b"content", "application/pdf")}
    upload_resp = await client.post("/api/upload", files=files)
    assert upload_resp.status_code == 200
    drawing_id = upload_resp.json()["id"]

    get_resp = await client.get(f"/api/drawings/{drawing_id}")
    assert get_resp.status_code == 200

    del_resp = await client.delete(f"/api/drawings/{drawing_id}")
    assert del_resp.status_code == 200

    get_resp2 = await client.get(f"/api/drawings/{drawing_id}")
    assert get_resp2.status_code == 404
