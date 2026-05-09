import asyncio
import base64
import re
import logging
from io import BytesIO
from typing import Dict, List, Any, Optional
from PIL import Image
from omegaconf import DictConfig
from langchain_core.messages import (
    HumanMessage, AIMessage, ToolMessage, SystemMessage, trim_messages
)

from app.state import AgentState
from app.llm import get_llm
from app.tools import ALL_TOOLS
import asyncio
import logging
from typing import Dict, List, Any, Optional
from omegaconf import DictConfig
from langchain_core.messages import (
    HumanMessage, AIMessage, ToolMessage, SystemMessage, trim_messages
)

from app.state import AgentState
from app.llm import get_llm
from app.tools import ALL_TOOLS
# ИМПОРТ ПРОМПТОВ
from app.prompts import get_final_system_prompt

logger = logging.getLogger(__name__)


async def preprocess_node(state: AgentState, cfg: DictConfig) -> AgentState:
    if not state.get("current_drawing"):
        return {"messages": [AIMessage(content="Ошибка: Чертеж не найден.")]}

    w = state.get("drawing_width", 0)
    h = state.get("drawing_height", 0)
    return {
        "drawing_context": f"Разрешение: {w}x{h}.",
        "analysis_complete": True
    }


async def agent_node(state: AgentState, cfg: DictConfig) -> AgentState:
    llm = get_llm(cfg)

    # 1. Используем импортированную функцию для сборки системного промпта
    heavy_data = state.get("heavy_analysis", "Данные пре-анализа отсутствуют.")
    rag_data = state.get("context", "Дополнительный контекст не найден.")

    sys_content = get_final_system_prompt(heavy_data, rag_data)

    # 2. Адаптация формата ответа под вопрос пользователя
    user_query = ""
    for m in reversed(state["messages"]):
        if isinstance(m, HumanMessage):
            user_query = str(m.content)
            break

    if any(word in user_query.lower() for word in ["подробно", "анализ", "опиши", "расскажи"]):
        format_instruction = "\n\nПРАВИЛО ОТВЕТА: Дай развернутый аналитический отчет с пояснениями."
    else:
        format_instruction = "\n\nПРАВИЛО ОТВЕТА: Дай краткий технический ответ."

    format_instruction += "\nВАЖНО: В конце ответа ОБЯЗАТЕЛЬНО выведи таблицу использованных ГОСТ/СНиП."

    # 3. Подготовка сообщений
    messages = state["messages"]
    trimmed_messages = trim_messages(
        messages,
        max_tokens=cfg.agent.get('max_history_tokens', 10000),
        strategy="last",
        token_counter=len,
        include_system=True,
        start_on="human"
    )

    # Начинаем список с системного сообщения
    final_messages = [SystemMessage(content=sys_content + format_instruction)]

    # Ищем индекс последнего сообщения от пользователя во всей истории
    last_human_idx = -1
    for i, msg in enumerate(trimmed_messages):
        if isinstance(msg, HumanMessage):
            last_human_idx = i

    for i, msg in enumerate(trimmed_messages):
        if i == last_human_idx and state.get("current_drawing"):
            # Модифицируем только ПОСЛЕДНИЙ HumanMessage, добавляя картинку (Vision)
            clean_b64 = state["current_drawing"].split('base64,')[-1]
            text_content = msg.content if isinstance(msg.content, str) else "Проанализируй чертеж."

            multimodal_msg = HumanMessage(
                content=[
                    {"type": "text", "text": text_content},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{clean_b64}"}}
                ]
            )
            final_messages.append(multimodal_msg)
        else:
            # Все остальные сообщения (AI, Tool, предыдущие Human) добавляем как есть
            final_messages.append(msg)

    # 4. Вызов LLM
    try:
        llm_with_tools = llm.bind_tools(ALL_TOOLS)
        response = await llm_with_tools.ainvoke(final_messages)
        return {"messages": [response]}
    except Exception as e:
        logger.error(f"LLM Error: {e}")
        return {"messages": [AIMessage(content="Ошибка нейросети при анализе.")]}



async def tools_node(state: AgentState) -> AgentState:
    """Выполнение инструментов, если агент решит уточнить что-то после 'тяжелого' пре-анализа."""
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

            # Синхронизация специфических полей
            if t_name == "extract_text":
                updates["ocr_text"] = str(result)
        except Exception as e:
            results.append(ToolMessage(content=f"Ошибка инструмента: {e}", tool_call_id=tool_call["id"]))

    updates["messages"] = results
    return updates


async def instructor_node(state: AgentState, cfg: DictConfig) -> AgentState:
    """Финальное структурирование ответа в схему Pydantic (если включено)."""
    if not cfg.run.get('use_instructor', False):
        return state

    try:
        from app.instructor.extractor import run_instructor
        from app.instructor.schemas import DrawingAnalysis

        # Получаем последний ответ от AIMessage
        last_ai_msg = ""
        for m in reversed(state["messages"]):
            if isinstance(m, AIMessage):
                last_ai_msg = m.content
                break

        # Если ответ уже есть, превращаем его в JSON-структуру
        result = await run_instructor(state, DrawingAnalysis)
        return {"final_output": result.dict() if result else None}
    except Exception as e:
        logger.error(f"Instructor Error: {e}")
        return state


def should_continue(state: AgentState, cfg: DictConfig):
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"
    if cfg.run.get('use_instructor', False):
        return "instructor"
    return "__end__"