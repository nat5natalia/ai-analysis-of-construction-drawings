import pytest
from unittest.mock import patch, MagicMock, AsyncMock

pytestmark = pytest.mark.asyncio


async def test_agent_run_success(agent):
    """Успешный запуск агента"""
    result = await agent.run("dummy.pdf", "Что на чертеже?")

    assert result["success"] is True
    assert result["answer"] == "Test answer"
    agent.drawing_knowledge.add_interaction_to_index.assert_called()


async def test_agent_run_caches_successful_response(agent):
    """Проверка, что успешный ответ сохраняется в кэш"""
    result = await agent.run("dummy.pdf", "Какие размеры?")

    assert result["success"] is True
    agent.cache.set.assert_called_once()


async def test_agent_run_returns_cached_response(agent):
    """Проверка, что при повторном вопросе возвращается кэш"""
    cached_response = {"success": True, "answer": "Cached answer"}
    agent.cache.get.return_value = cached_response

    result = await agent.run("dummy.pdf", "Тот же вопрос")

    assert result == cached_response
    agent.graph.ainvoke.assert_not_called()


async def test_agent_run_handles_missing_drawing(agent):
    """Чертёж не найден → ошибка"""
    agent.drawing_knowledge.load_drawing_and_cache.side_effect = ValueError("File not found")

    result = await agent.run("nonexistent.pdf", "Вопрос")

    assert result["success"] is False
    assert "error" in result


async def test_agent_run_handles_graph_failure(agent):
    """Ошибка в графе LangGraph → возвращает ошибку"""
    agent.graph.ainvoke.side_effect = Exception("LangGraph error")

    result = await agent.run("dummy.pdf", "Вопрос")

    assert result["success"] is False
    assert "error" in str(result["error"]).lower()


async def test_pre_analyze_success(agent):
    """Успешный предварительный анализ"""
    with patch("asyncio.get_running_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value={
            "image_base64": "fake",
            "ocr_text": "text",
            "width": 100,
            "height": 100
        })

        result = await agent.pre_analyze("test.pdf", page=0)

        assert result["success"] is True
        agent.drawing_knowledge.save_heavy_analysis.assert_called()