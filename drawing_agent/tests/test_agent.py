import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from langchain_core.messages import AIMessage

pytestmark = pytest.mark.asyncio


async def test_agent_run_success(agent):
    """Успешный запуск агента"""
    with patch("app.agent.build_graph") as mock_build_graph:
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "messages": [AIMessage(content="Test answer")]
        })
        mock_build_graph.return_value = mock_graph

        with patch("app.agent.DrawingKnowledgeManager") as MockKnowledge:
            mock_knowledge = MagicMock()
            mock_knowledge.load_drawing_and_cache = MagicMock(return_value={
                "image_base64": "fake_base64",
                "ocr_text": "test ocr",
                "width": 100,
                "height": 100
            })
            mock_knowledge.get_heavy_analysis = MagicMock(return_value=None)
            MockKnowledge.return_value = mock_knowledge

            from app.agent import DrawingAgent
            test_agent = DrawingAgent(agent.cfg, vector_db=agent.vector_db)
            test_agent.graph = mock_graph
            test_agent.drawing_knowledge = mock_knowledge
            test_agent.cache = MagicMock()
            test_agent.cache.get.return_value = None

            result = await test_agent.run("dummy.pdf", "Что на чертеже?")

            assert result["success"] is True
            assert result["answer"] == "Test answer"
            mock_knowledge.add_interaction_to_index.assert_called()


async def test_agent_run_caches_successful_response(agent):
    """Проверка, что успешный ответ сохраняется в кэш"""
    with patch("app.agent.build_graph") as mock_build_graph:
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "messages": [AIMessage(content="Test answer")]
        })
        mock_build_graph.return_value = mock_graph

        with patch("app.agent.DrawingKnowledgeManager") as MockKnowledge:
            mock_knowledge = MagicMock()
            mock_knowledge.load_drawing_and_cache = MagicMock(return_value={
                "image_base64": "fake_base64",
                "ocr_text": "test ocr",
                "width": 100,
                "height": 100
            })
            mock_knowledge.get_heavy_analysis = MagicMock(return_value=None)
            MockKnowledge.return_value = mock_knowledge

            from app.agent import DrawingAgent
            test_agent = DrawingAgent(agent.cfg, vector_db=agent.vector_db)
            test_agent.graph = mock_graph
            test_agent.drawing_knowledge = mock_knowledge
            test_agent.cache = MagicMock()
            test_agent.cache.get.return_value = None

            result = await test_agent.run("dummy.pdf", "Какие размеры?")

            assert result["success"] is True
            test_agent.cache.set.assert_called_once()


async def test_agent_run_returns_cached_response(agent):
    """Проверка, что при повторном вопросе возвращается кэш"""
    cached_response = {"success": True, "answer": "Cached answer"}
    agent.cache.get.return_value = cached_response

    result = await agent.run("dummy.pdf", "Тот же вопрос")

    assert result == cached_response


async def test_agent_run_handles_missing_drawing(agent):
    """Чертёж не найден → ошибка"""
    agent.drawing_knowledge.load_drawing_and_cache.side_effect = ValueError("File not found")

    result = await agent.run("nonexistent.pdf", "Вопрос")

    assert result["success"] is False
    assert "error" in result


async def test_agent_run_handles_graph_failure(agent):
    """Ошибка в графе LangGraph → возвращает ошибку"""
    with patch("app.agent.build_graph") as mock_build_graph:
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(side_effect=Exception("LangGraph error"))
        mock_build_graph.return_value = mock_graph

        from app.agent import DrawingAgent
        test_agent = DrawingAgent(agent.cfg, vector_db=agent.vector_db)
        test_agent.graph = mock_graph
        test_agent.drawing_knowledge = agent.drawing_knowledge
        test_agent.cache = agent.cache

        result = await test_agent.run("dummy.pdf", "Вопрос")

        assert result["success"] is False
        assert "error" in str(result.get("error", "")).lower()


async def test_pre_analyze_success(agent):
    """Успешный предварительный анализ"""
    with patch("app.agent.DrawingKnowledgeManager") as MockKnowledge:
        mock_knowledge = MagicMock()
        mock_knowledge.load_drawing_and_cache = MagicMock(return_value={
            "image_base64": "fake_base64",
            "ocr_text": "test ocr",
            "width": 100,
            "height": 100
        })
        mock_knowledge.get_heavy_analysis = MagicMock(return_value=None)
        mock_knowledge.save_heavy_analysis = MagicMock()
        MockKnowledge.return_value = mock_knowledge

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value={
                "image_base64": "fake",
                "ocr_text": "text",
                "width": 100,
                "height": 100
            })

            from app.agent import DrawingAgent
            test_agent = DrawingAgent(agent.cfg, vector_db=agent.vector_db)
            test_agent.drawing_knowledge = mock_knowledge

            result = await test_agent.pre_analyze("test.pdf", drawing_id="test_id", page=0)

            assert result["success"] is True
            # Этот тест падает, потому что save_heavy_analysis не вызывается
            # Это баг в коде агента, который нужно исправить разработчикам
            mock_knowledge.save_heavy_analysis.assert_called_once()