import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from omegaconf import OmegaConf


@pytest.fixture
def mock_cfg():
    """Базовая конфигурация для тестов (с секцией run)"""
    return OmegaConf.create({
        "data_dir": "./test_data",
        "model": {
            "name": "qwen",
            "max_tokens": 2000
        },
        "run": {
            "use_instructor": False
        }
    })


@pytest.fixture
def mock_vector_db():
    """Мок векторной БД"""
    mock = MagicMock()
    mock.add = MagicMock()
    mock.search = MagicMock(return_value=[])
    mock.index = MagicMock()
    mock.index.ntotal = 0
    return mock


@pytest.fixture
def mock_embedding_generator():
    """Мок генератора эмбеддингов"""
    with patch("rag.embeddings.EmbeddingGenerator") as mock:
        instance = MagicMock()
        instance.generate.return_value = [0.1, 0.2, 0.3]
        mock.return_value = instance
        yield mock


@pytest.fixture
def mock_tools():
    """Мок всех инструментов (YOLO, OpenCV, OCR)"""
    with patch("app.tools.detect_yolo_objects") as mock_yolo, \
         patch("app.tools.extract_dimensions") as mock_dim, \
         patch("app.tools.detect_holes") as mock_holes, \
         patch("app.tools.detect_tables") as mock_tables, \
         patch("app.tools.extract_text") as mock_ocr:

        mock_yolo.invoke.return_value = {"objects": ["column", "beam"]}
        mock_dim.invoke.return_value = {"width": 600, "height": 400}
        mock_holes.invoke.return_value = {"holes": []}
        mock_tables.invoke.return_value = {"tables": []}
        mock_ocr.invoke.return_value = "Full OCR text content"

        yield {
            "yolo": mock_yolo,
            "dim": mock_dim,
            "holes": mock_holes,
            "tables": mock_tables,
            "ocr": mock_ocr
        }


@pytest_asyncio.fixture(scope="function")
async def agent(mock_cfg, mock_vector_db, mock_embedding_generator, mock_tools):
    """Создание экземпляра DrawingAgent с моками"""
    from app.agent import DrawingAgent

    with patch("app.agent.AsyncSqliteSaver") as mock_saver:
        mock_saver.from_conn_string.return_value.__aenter__ = AsyncMock()
        mock_saver.from_conn_string.return_value.__aexit__ = AsyncMock()

        agent = DrawingAgent(mock_cfg, vector_db=mock_vector_db)
        
        # Мок графа LangGraph
        agent.graph = MagicMock()
        agent.graph.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content="Test answer", type="ai")]
        })
        
        # Мок менеджера знаний
        agent.drawing_knowledge = MagicMock()
        agent.drawing_knowledge._get_drawing_hash = MagicMock(return_value="test_hash_123")
        agent.drawing_knowledge.load_drawing_and_cache = MagicMock(return_value={
            "image_base64": "fake_base64",
            "ocr_text": "test ocr",
            "width": 100,
            "height": 100
        })
        agent.drawing_knowledge.get_heavy_analysis = MagicMock(return_value=None)
        agent.drawing_knowledge.initialize_static_knowledge = MagicMock()
        agent.drawing_knowledge.retrieve_context = MagicMock(return_value="RAG context")
        agent.drawing_knowledge.add_interaction_to_index = MagicMock()
        agent.drawing_knowledge.save_heavy_analysis = MagicMock()
        
        # Мок кэша
        agent.cache = MagicMock()
        agent.cache.get.return_value = None
        agent.cache.set = MagicMock()

        yield agent