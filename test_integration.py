import pytest
import asyncio
import os
from httpx import AsyncClient, ASGITransport
from main import app
from db import drawings
from vector_db import vector_db

def run_async(coro):
    """Запускает асинхронную корутину в отдельном событийном цикле."""
    return asyncio.run(coro)

@pytest.fixture(autouse=True)
def cleanup():
    """Синхронная фикстура очистки после каждого теста."""
    yield
    async def _clean():
        await drawings.delete_many({})
        vector_db.index.reset()
        vector_db.metadata.clear()
        vector_db._save()
        upload_dir = "uploads"
        if os.path.exists(upload_dir):
            for f in os.listdir(upload_dir):
                file_path = os.path.join(upload_dir, f)
                if os.path.isfile(file_path):
                    os.remove(file_path)
    run_async(_clean())

# ---- Тесты ----
def test_upload_png():
    async def _test():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82'
            files = {"file": ("test.png", png_data, "image/png")}
            response = await client.post("/api/upload", files=files)
            assert response.status_code == 200
            data = response.json()
            assert "id" in data
            assert data["status"] == "uploaded"
            drawing_id = data["id"]
            await asyncio.sleep(2)
            resp_desc = await client.get(f"/api/describe/{drawing_id}")
            assert resp_desc.status_code == 200
            desc_data = resp_desc.json()
            assert "description" in desc_data
            assert desc_data["description"].startswith("[DS] Описание чертежа")
    run_async(_test())

def test_upload_pdf():
    async def _test():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            pdf_data = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000010 00000 n \n0000000059 00000 n \n0000000114 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n178\n%%EOF'
            files = {"file": ("test.pdf", pdf_data, "application/pdf")}
            response = await client.post("/api/upload", files=files)
            assert response.status_code == 200
            drawing_id = response.json()["id"]
            await asyncio.sleep(2)
            resp_desc = await client.get(f"/api/describe/{drawing_id}")
            assert resp_desc.status_code == 200
            assert "description" in resp_desc.json()
    run_async(_test())

def test_ask():
    async def _test():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82'
            files = {"file": ("test.png", png_data, "image/png")}
            resp_upload = await client.post("/api/upload", files=files)
            drawing_id = resp_upload.json()["id"]
            await asyncio.sleep(2)
            resp_ask = await client.post(f"/api/ask/{drawing_id}", json={"question": "Что изображено?"})
            assert resp_ask.status_code == 200
            data = resp_ask.json()
            assert data["question"] == "Что изображено?"
            assert data["answer"].startswith("[DS] Ответ на вопрос")
    run_async(_test())

def test_search():
    async def _test():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82'
            for _ in range(2):
                files = {"file": ("test.png", png_data, "image/png")}
                await client.post("/api/upload", files=files)
            await asyncio.sleep(2)
            resp_search = await client.get("/api/search", params={"q": "test", "limit": 5})
            assert resp_search.status_code == 200
            data = resp_search.json()
            assert "results" in data
            assert "total" in data
            assert isinstance(data["results"], list)
    run_async(_test())

def test_similar():
    async def _test():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82'
            files1 = {"file": ("test1.png", png_data, "image/png")}
            resp1 = await client.post("/api/upload", files=files1)
            id1 = resp1.json()["id"]
            files2 = {"file": ("test2.png", png_data, "image/png")}
            await client.post("/api/upload", files=files2)
            await asyncio.sleep(2)
            resp_similar = await client.get(f"/api/similar/{id1}", params={"limit": 5})
            assert resp_similar.status_code == 200
            data = resp_similar.json()
            assert "drawing_id" in data
            assert "similar" in data
            assert isinstance(data["similar"], list)
    run_async(_test())

def test_list_drawings():
    async def _test():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82'
            files = {"file": ("test.png", png_data, "image/png")}
            await client.post("/api/upload", files=files)
            await asyncio.sleep(1)
            resp_list = await client.get("/api/drawings")
            assert resp_list.status_code == 200
            data = resp_list.json()
            assert "total" in data
            assert "drawings" in data
            assert data["total"] >= 1
    run_async(_test())

def test_delete_drawing():
    async def _test():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82'
            files = {"file": ("test.png", png_data, "image/png")}
            resp_upload = await client.post("/api/upload", files=files)
            drawing_id = resp_upload.json()["id"]
            await asyncio.sleep(1)
            resp_delete = await client.delete(f"/api/drawings/{drawing_id}")
            assert resp_delete.status_code == 200
            resp_get = await client.get(f"/api/drawings/{drawing_id}")
            assert resp_get.status_code == 404
    run_async(_test())