import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.agent import DrawingAgent


@pytest.mark.asyncio
async def test_agent_run_success():
    cfg = MagicMock()
    mock_vdb = MagicMock()

    # Мокаем менеджер знаний, чтобы не грузить реальные PDF
    with patch("app.agent.DrawingKnowledgeManager") as MockManager:
        instance = MockManager.return_value
        instance.load_drawing_and_cache.return_value = {
            "image_base64": "fake_base64",
            "ocr_text": "text",
            "width": 100, "height": 100
        }

        agent = DrawingAgent(cfg, vector_db=mock_vdb)
        # Мокаем граф LangGraph
        agent.graph.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content="Итоговый ответ от ИИ", type="ai")]
        })

        result = await agent.run("dummy.pdf", "Что на чертеже?")

        assert result["success"] is True
        assert result["answer"] == "Итоговый ответ от ИИ"
        # Проверяем, что ответ попал в индекс для RAG
        instance.add_interaction_to_index.assert_called()