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

    heavy_data = state.get("heavy_analysis", "Данные пре-анализа отсутствуют.")
    rag_data = state.get("context", "Дополнительный контекст не найден.")
    sys_content = get_final_system_prompt(heavy_data, rag_data)

    messages = state.get("messages", [])
    user_query = ""

    # Безопасный поиск последнего вопроса пользователя
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            if isinstance(m.content, str):
                user_query = m.content
                break
            elif isinstance(m.content, list):
                user_query = " ".join([str(item.get("text", "")) for item in m.content if item.get("type") == "text"])
                break

    is_detailed = any(word in user_query.lower() for word in ["подробно", "анализ", "опиши", "расскажи"])

    format_instruction = (
        "\n\nСТРУКТУРА ОТВЕТА:"
        "\n1. ПРЯМОЙ КРАТКИЙ ОТВЕТ (максимум 2-3 предложения)."
        f"\n2. {'РАЗВЕРНУТЫЙ АНАЛИЗ' if is_detailed else 'ТЕХНИЧЕСКИЕ ПОДРОБНОСТИ'} (если уместно)."
        "\n3. ТАБЛИЦА ГОСТ/СНиП."
        "\n\nВАЖНО: Пиши максимально лаконично. Если ответ требует много места - сокращай материалы"
    )

    # --- ИСПРАВЛЕННЫЙ БЛОК ПОДГОТОВКИ СООБЩЕНИЙ ---
    text_only_messages = []
    for m in messages:
        # Пропускаем ToolMessage, так как они не нужны для trim
        if isinstance(m, ToolMessage):
            continue
            
        content_text = ""
        
        # Безопасное извлечение контента
        if hasattr(m, 'content'):
            if isinstance(m.content, str):
                content_text = m.content if m.content else "..."
            elif isinstance(m.content, list):
                # Извлекаем только текст, игнорируя картинки
                text_parts = []
                for item in m.content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_parts.append(str(item.get("text", "")))
                    elif hasattr(item, 'get'):
                        if item.get("type") == "text":
                            text_parts.append(str(item.get("text", "")))
                content_text = " ".join(text_parts) if text_parts else "..."
        else:
            content_text = "..."
        
        # Если контент пустой или None
        if not content_text or content_text.strip() == "":
            content_text = "..."
        
        # Создаем копию сообщения только с текстом
        try:
            # Определяем тип сообщения
            if isinstance(m, HumanMessage):
                new_msg = HumanMessage(content=content_text)
            elif isinstance(m, AIMessage):
                new_msg = AIMessage(content=content_text)
                # Сохраняем tool_calls если есть
                if hasattr(m, "tool_calls") and m.tool_calls:
                    new_msg.tool_calls = m.tool_calls
            else:
                continue  # Пропускаем неизвестные типы
            
            text_only_messages.append(new_msg)
        except Exception as e:
            logger.warning(f"Failed to create message copy: {e}")
            continue

    # Обрезка сообщений с безопасной обработкой
    try:
        if text_only_messages:
            trimmed_messages = trim_messages(
                text_only_messages,
                max_tokens=cfg.agent.get('max_history_tokens', 4000),
                strategy="last",
                token_counter=llm.get_num_tokens,
                include_system=False,
                start_on="human"
            )
        else:
            trimmed_messages = []
    except Exception as e:
        logger.error(f"Trim Error: {e}")
        # Берем последние 3 сообщения как fallback
        trimmed_messages = text_only_messages[-3:] if len(text_only_messages) > 3 else text_only_messages

    final_messages = [SystemMessage(content=sys_content + format_instruction)]

    # Находим последний HumanMessage для прикрепления картинки
    last_human_idx = -1
    for i, msg in enumerate(trimmed_messages):
        if isinstance(msg, HumanMessage):
            last_human_idx = i

    for i, msg in enumerate(trimmed_messages):
        if i == last_human_idx and state.get("current_drawing"):
            # Очистка base64 и безопасное формирование контента
            raw_b64 = state["current_drawing"]
            clean_b64 = raw_b64.split('base64,')[-1] if 'base64,' in raw_b64 else raw_b64

            text_val = msg.content if isinstance(msg.content, str) else "Проанализируй этот чертеж."

            multimodal_msg = HumanMessage(
                content=[
                    {"type": "text", "text": text_val},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{clean_b64}"}}
                ]
            )
            final_messages.append(multimodal_msg)
        else:
            final_messages.append(msg)

    try:
        response = await llm.ainvoke(final_messages)
        return {"messages": [response]}
    except Exception as e:
        logger.error(f"LLM Invocation Error: {e}")
        return {"messages": [AIMessage(content="Ошибка при вызове LLM. Попробуйте сократить запрос.")]}

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