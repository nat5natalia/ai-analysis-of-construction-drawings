import pytest
from worker import process_drawing

pytestmark = pytest.mark.anyio


class TestIntegration:
    """Интеграционные тесты (проверяют связку worker → agent → БД)"""

    @pytest.mark.skip(reason="Требует запущенных redis, mongodb, agent")
    async def test_full_flow_real_services(self):
        """Полный интеграционный тест с реальными сервисами (запускать отдельно)"""
        # Этот тест нужно запускать только когда все сервисы подняты
        # docker-compose up -d
        # pytest celery_worker/tests/test_integration.py -v
        pass

    def test_task_module_can_be_imported(self):
        """Проверка, что модуль worker импортируется без ошибок"""
        import worker
        assert worker is not None
        assert hasattr(worker, "process_drawing")

    def test_worker_has_required_functions(self):
        """Проверка наличия необходимых функций в worker"""
        assert callable(process_drawing)
        # Если в worker.py есть другие важные функции, проверяем их
        # assert hasattr(worker, "wait_for_agent")