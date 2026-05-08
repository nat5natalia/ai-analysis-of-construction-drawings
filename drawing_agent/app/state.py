from typing import TypedDict, Annotated, List, Any, Optional, Dict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """
    Объект состояния графа (State).
    Используется для передачи данных между узлами (nodes).
    """
    # История сообщений с механизмом накопления (add_messages)
    messages: Annotated[List[BaseMessage], add_messages]

    # Изображение и его метаданные
    current_drawing: Optional[str]  # Base64 строка
    drawing_width: int
    drawing_height: int
    page: int

    # Текстовые данные
    ocr_text: str  # Текст, полученный через EasyOCR
    context: str  # Контекст из векторной базы (RAG)

    # --- ПРЕДВЫЧИСЛЕННЫЕ ДАННЫЕ (Heavy Analysis) ---
    # Сюда записываются результаты всех инструментов, запущенных до старта агента
    heavy_analysis: Optional[str]

    # Результаты работы инструментов (структурированные)
    tool_results: Dict[str, Any]
    yolo_detection: Dict[str, Any]
    extracted_holes: List[Dict[str, Any]]
    extracted_dimensions: Dict[str, Any]
    extracted_objects: List[Dict[str, Any]]

    # Технические флаги и контекст для LLM
    drawing_context: Optional[str]  # Краткое описание для SystemMessage
    analysis_complete: bool  # Флаг завершения препроцессинга

    # Параметры управления (опционально)
    wait_time: int
    max_retries: int

    # Финальный результат (после Instructor)
    final_output: Optional[Dict[str, Any]]