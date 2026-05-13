import logging
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from app.llm import get_llm
from app.prompts import SYSTEM_INSTRUCTOR
from app.instructor.builder import build_instructor_input

logger = logging.getLogger(__name__)
async def run_instructor(state, schema):
    last_ai_message = ""
    for m in reversed(state.get("messages", [])):
        if isinstance(m, AIMessage) and m.content:
            last_ai_message = m.content
            break

    heavy_data = state.get("heavy_analysis", "")

    # Собираем лаконичный вход для инструктора
    input_text = f"""
    ДАННЫЕ АНАЛИЗА:
    {heavy_data}

    ПОСЛЕДНИЙ ОТВЕТ ИНЖЕНЕРА:
    {last_ai_message}
    """

    llm = get_llm()

    # 2. Настраиваем структурированный вывод с контролем токенов
    # Важно: некоторые провайдеры требуют передачи параметров через bind или config
    structured_llm = llm.with_structured_output(schema)

    messages = [
        ("system", SYSTEM_INSTRUCTOR),
        ("human", input_text)
    ]

    try:
        # 3. Вызов с ограничением времени и токенов
        return await structured_llm.ainvoke(
            messages,
            config={"max_tokens": 2000}  # Ограничиваем размер самого JSON
        )
    except Exception as e:
        # Если не удалось распарсить (например, из-за длины), логируем ошибку
        # и возвращаем None, чтобы цепочка LangGraph не упала
        logger.error(f"Instructor parsing failed: {e}")
        return None