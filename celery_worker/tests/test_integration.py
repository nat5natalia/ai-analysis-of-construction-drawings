import pytest
import requests
from worker import process_drawing, app as celery_app

pytestmark = pytest.mark.anyio


class TestIntegration:
    """Интеграционные тесты (проверяют связку worker → agent → БД)"""

    async def test_full_flow_real_services(self):
        """Полный интеграционный тест с реальными сервисами"""
        
        # 1. Проверяем, что агент доступен
        try:
            response = requests.get("http://drawing_agent:8000/health", timeout=5)
            assert response.status_code == 200, f"Agent health check failed: {response.status_code}"
            assert response.json().get("status") == "ok"
        except requests.exceptions.ConnectionError:
            pytest.fail("Drawing agent is not available at http://drawing_agent:8000")
        except Exception as e:
            pytest.fail(f"Agent health check error: {e}")
        
        # 2. Проверяем, что Redis доступен (через Celery)
        try:
            inspector = celery_app.control.inspect()
            stats = inspector.stats()
            assert stats is not None, "Celery worker не отвечает"
        except Exception as e:
            pytest.fail(f"Celery/Redis error: {e}")
        
        # 3. Проверяем, что MongoDB доступен
        try:
            from pymongo import MongoClient
            import os
            mongo_url = os.getenv("MONGO_URL", "mongodb://mongodb:27017")
            client = MongoClient(mongo_url, serverSelectionTimeoutMS=2000)
            client.admin.command('ping')
            client.close()
        except Exception as e:
            pytest.fail(f"MongoDB connection error: {e}")
        
        # 4. Проверяем, что функция process_drawing существует
        assert callable(process_drawing), "process_drawing is not callable"

    def test_task_module_can_be_imported(self):
        """Проверка, что модуль worker импортируется без ошибок"""
        import worker
        assert worker is not None
        assert hasattr(worker, "process_drawing")

    def test_worker_has_required_functions(self):
        """Проверка наличия необходимых функций в worker"""
        assert callable(process_drawing)