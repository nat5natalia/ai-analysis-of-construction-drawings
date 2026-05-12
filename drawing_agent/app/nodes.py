import asyncio
import logging
from typing import Dict, List, Any, Optional

from langchain_core.messages import (
    HumanMessage, AIMessage, ToolMessage, SystemMessage, trim_messages, BaseMessage
)
from omegaconf import DictConfig

from app.state import AgentState
from app.llm import get_llm
from app.tools import ALL_TOOLS
from app.prompts import get_final_system_prompt
from app.instructor.extractor import run_instructor
from app.instructor.schemas import DrawingAnalysis

logger = logging.getLogger(__name__)


async def preprocess_node(state: AgentState, cfg: DictConfig) -> AgentState:
    """
    Подготовительный узел: проверяет наличие чертежа и готовит метаданные контекста.
    """
    if not state.get("current_drawing"):
        return {"messages": [AIMessage(content="Ошибка: Чертеж не найден.")]}

    w = state.get("drawing_width", 0)
    h = state.get("drawing_height", 0)

    return {
        "drawing_context": f"Разрешение: {w}x{h}.",
        "analysis_complete": True
    }


async def agent_node(state: AgentState, cfg: DictConfig) -> AgentState:
    """
    Основной узел агента: формирует промпт, обрезает историю и вызывает LLM.
    """
    llm = get_llm(cfg)

    # 1. Сбор данных из стейта (результаты OCR, YOLO и RAG)
    heavy_data = state.get("heavy_analysis", "Данные пре-анализа отсутствуют.")
    rag_data = state.get("context", "Дополнительный контекст не найден.")
    sys_content = get_final_system_prompt(heavy_data, rag_data)

    # 2. Анализ намерения пользователя (краткий или подробный ответ)
    messages = state.get("messages", [])
    user_query = ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage) and isinstance(m.content, str):
            user_query = m.content
            break

    is_detailed = any(word in user_query.lower() for word in ["подробно", "анализ", "опиши", "расскажи"])

    format_instruction = (

        "\n\nСТРУКТУРА ОТВЕТА:"

        "\n1. ПРЯМОЙ КРАТКИЙ ОТВЕТ (максимум 2-3 предложения)."

        f"\n2. {'РАЗВЕРНУТЫЙ АНАЛИЗ' if is_detailed else 'ТЕХНИЧЕСКИЕ ПОДРОБНОСТИ'} (если уместно)."

        "\n3. ТАБЛИЦА ГОСТ/СНиП."

        "\n\nВАЖНО: Пиши максимально лаконично. Если ответ требует много места, сокращай описание материалов."

    )
    # 3. ПОДГОТОВКА К ОБРЕЗКЕ (Решение проблемы TypeError)
    # tiktoken падает, если видит список (картинку) или None.
    # Поэтому мы создаем временный список только с текстовым контентом для обрезки.
    text_only_messages = []
    for m in messages:
        # Если контент — список (мультимодальное сообщение), берем только текстовую часть
        if isinstance(m.content, list):
            text_content = next((item["text"] for item in m.content if item["type"] == "text"), "")
            text_only_messages.append(HumanMessage(content=text_content))
        elif m.content is None:
            text_only_messages.append(m.__class__(content=""))
        else:
            text_only_messages.append(m)

    # Обрезаем историю, используя только текстовые версии сообщений
    try:
        trimmed_messages = trim_messages(
            text_only_messages,
            max_tokens=cfg.agent.get('max_history_tokens', 4000),
            strategy="last",
            token_counter=llm.get_num_tokens,  # Теперь здесь всегда строки
            include_system=False,
            start_on="human"
        )
    except Exception as e:
        logger.error(f"Trim Error: {e}")
        trimmed_messages = text_only_messages[-5:]  # Фолбэк: просто последние 5 сообщений

    # 4. ФОРМИРОВАНИЕ ИТОГОВОГО СПИСКА (Добавляем системный промпт и картинку)
    final_messages = [SystemMessage(content=sys_content + format_instruction)]

    # Индекс последнего сообщения от человека в ОБРЕЗАННОМ списке
    last_human_idx = -1
    for i, msg in enumerate(trimmed_messages):
        if isinstance(msg, HumanMessage):
            last_human_idx = i

    for i, msg in enumerate(trimmed_messages):
        # Добавляем изображение ТОЛЬКО к самому последнему HumanMessage
        if i == last_human_idx and state.get("current_drawing"):
            clean_b64 = state["current_drawing"].split('base64,')[-1]
            # Гарантируем, что текст — это строка
            text_content = msg.content if isinstance(msg.content, str) else "Проанализируй этот чертеж."

            multimodal_msg = HumanMessage(
                content=[
                    {"type": "text", "text": text_content},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{clean_b64}"}}
                ]
            )
            final_messages.append(multimodal_msg)
        else:
            final_messages.append(msg)

    # 5. Вызов нейросети
    try:
        # Передаем собранный пакет (System + History + Image)
        response = await llm.ainvoke(final_messages)
        return {"messages": [response]}
    except Exception as e:
        logger.error(f"LLM Invocation Error: {e}")
        return {"messages": [AIMessage(content="Произошла ошибка при обращении к нейросети. Попробуйте позже.")]}


async def tools_node(state: AgentState) -> AgentState:
    """
    Узел выполнения инструментов (Tool Use).
    """
    last_message = state["messages"][-1]
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return state

    results = []
    updates = {}

    for tool_call in last_message.tool_calls:
        t_name = tool_call["name"]
        t_args = tool_call["args"]
        try:
            tool = next((t for t in ALL_TOOLS if t.name == t_name), None)
            if not tool:
                result = f"Error: Tool {t_name} not found."
            else:
                result = await tool.ainvoke(t_args)

            results.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

            # Если инструмент извлекал текст, сохраняем его в отдельное поле для удобства
            if t_name == "extract_text":
                updates["ocr_text"] = str(result)
        except Exception as e:
            results.append(ToolMessage(content=f"Ошибка инструмента {t_name}: {e}", tool_call_id=tool_call["id"]))

    updates["messages"] = results
    return updates


async def instructor_node(state: AgentState, cfg: DictConfig) -> AgentState:
    """
    Узел структурирования данных (Instructor).
    Вызывается в конце, чтобы превратить неструктурированный ответ в JSON схему DrawingAnalysis.
    """
    if not cfg.run.get('use_instructor', False):
        return state

    try:
        # run_instructor анализирует state и заполняет Pydantic-модель
        result = await run_instructor(state, DrawingAnalysis)
        return {"final_output": result.dict() if result else None}
    except Exception as e:
        logger.error(f"Instructor Node Error: {e}")
        return {"final_output": None}


def should_continue(state: AgentState, cfg: DictConfig):
    """
    Условная логика переходов в графе.
    """
    last_msg = state["messages"][-1]

    # Если LLM решила вызвать функцию (tool_calls)
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"

    # Если инструментов нет, но нам нужен структурированный JSON на выходе
    if cfg.run.get('use_instructor', False):
        return "instructor"

    # Иначе завершаем работу
    return "__end__"