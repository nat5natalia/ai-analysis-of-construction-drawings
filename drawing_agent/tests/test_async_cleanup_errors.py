from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from omegaconf import OmegaConf

from app.agent import DrawingAgent
from app.nodes import agent_node

pytestmark = pytest.mark.asyncio


def _cfg():
    return OmegaConf.create({
        "agent": {
            "max_history_tokens": 4000,
            "max_response_tokens": 2048,
        },
        "model": {},
        "run": {
            "use_instructor": False,
        },
        "data_dir": "./test_data",
    })


async def test_agent_node_handles_async_generator_aclose_error():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=RuntimeError("aclose(): asynchronous generator is already running"))

    state = {
        "messages": [HumanMessage(content="Describe the drawing")],
        "current_drawing": "fake_base64",
        "drawing_width": 100,
        "drawing_height": 100,
    }

    with patch("app.nodes.get_llm", return_value=llm):
        result = await agent_node(state, _cfg())

    assert isinstance(result["messages"][0], AIMessage)
    assert result["messages"][0].content


async def test_agent_run_normalizes_graph_aclose_error(mock_cfg, mock_vector_db):
    agent = DrawingAgent(mock_cfg, vector_db=mock_vector_db)
    agent._initialized = True
    agent.graph = MagicMock()
    agent.graph.ainvoke = AsyncMock(side_effect=RuntimeError("aclose(): asynchronous generator is already running"))
    agent.cache = MagicMock()
    agent.cache.get.return_value = None
    agent.drawing_knowledge = MagicMock()
    agent.drawing_knowledge.load_drawing_and_cache.return_value = {
        "image_base64": "fake_base64",
        "ocr_text": "text",
        "width": 100,
        "height": 100,
    }
    agent.drawing_knowledge.get_heavy_analysis.return_value = "cached analysis"
    agent.drawing_knowledge.retrieve_context.return_value = "context"

    result = await agent.run("dummy.pdf", "Describe the drawing")

    assert result["success"] is False
    assert result["error"] == "LLM connection failed during analysis"
