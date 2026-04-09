from typing import TypedDict, List, Optional, Any


class AgentState(TypedDict):
    """
    Глобальное состояние агента (память)
    """

    # история сообщений LLM
    messages: List[Any]

    # данные входа
    image_base64: str
    ocr_text: str

    # RAG
    context: str

    page: int

    # финальный результат
    final_output: Optional[dict]