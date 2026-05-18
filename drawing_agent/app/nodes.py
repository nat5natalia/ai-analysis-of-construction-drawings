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


def estimate_message_tokens(messages: List[BaseMessage]) -> int:
    total_chars = 0
    for message in messages:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            total_chars += sum(len(str(item.get("text", item))) for item in content)
        else:
            total_chars += len(str(content))

    return max(1, total_chars // 4)


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
    Основной узел агента: очищает историю от метаданных БД, 
    прикрепляет чертеж ТОЛЬКО к последнему вопросу, обрезает контекст и вызывает LLM.
    """
    llm = get_llm(cfg)

    heavy_data = state.get("heavy_analysis", "Данные пре-анализа отсутствуют.")
    rag_data = state.get("context", "Дополнительный контекст не найден.")
    
    # 1. Формируем чистый системный промпт (Краткость + ГОСТы)
    sys_content = get_final_system_prompt(heavy_data, rag_data)
    format_instruction = (
        "\n\nПРАВИЛА ОФОРМЛЕНИЯ ОТВЕТА:\n"
        "1. Отвечай максимально КРАТКО и строго по существу. Никакой «воды» и общих вводных фраз.\n"
        "2. Структура: Сначала прямой технический ответ (2-3 предложения), затем краткие детали.\n"
        "3. В самом конце ответа ОБЯЗАТЕЛЬНО выведи таблицу или список применимых ГОСТов и СНиП.\n"
        "Если информации на чертеже мало — не выдумывай, пиши только то, что видишь."
    )

    messages = state.get("messages", [])
    
    # 2. КРИСТАЛЬНАЯ ОЧИСТКА: Маппим историю из БД/Стейта в чистые объекты LangChain
    # Полностью убираем ts, id, status и прочие метаданные, съедающие токены
    # --- ИСПРАВЛЕННЫЙ БЛОК ПОДГОТОВКИ СООБЩЕНИЙ ---
    text_only_messages = []
    for m in messages:
        if isinstance(m, SystemMessage):
            continue  # Старые системные инструкции нам не нужны, мы добавим свежую
            
        # Извлекаем только текст
        content_text = ""
        if isinstance(m.content, str):
            content_text = m.content
        elif isinstance(m.content, list):
            parts = [str(item.get("text", "")) for item in m.content if item.get("type") == "text"]
            content_text = " ".join(parts)

        if not content_text.strip() and not hasattr(m, "tool_calls"):
            continue # Пропускаем пустые сообщения без вызовов инструментов

        # Строгое сохранение типов без мусора
        if isinstance(m, HumanMessage) or (isinstance(m, dict) and m.get("role") == "user"):
            text_only_messages.append(HumanMessage(content=content_text))
        elif isinstance(m, AIMessage) or (isinstance(m, dict) and m.get("role") in ["assistant", "agent"]):
            text_only_messages.append(AIMessage(content=content_text, tool_calls=getattr(m, "tool_calls", None)))
        elif isinstance(m, ToolMessage) or (isinstance(m, dict) and m.get("role") == "tool"):
            t_id = getattr(m, "tool_call_id", "") or m.get("tool_call_id", "")
            text_only_messages.append(ToolMessage(content=content_text, tool_call_id=t_id))

    # 3. БЕЗОПАСНАЯ ОБРЕЗКА: Контролируем лимит контекста истории
    try:
        trimmed_messages = trim_messages(
            text_only_messages,
            max_tokens=cfg.agent.get('max_history_tokens', 4000),
            strategy="last",
            token_counter=estimate_message_tokens,
            include_system=False,
            start_on="human"  # Автоматически режет оторванные ToolMessage сверху
        )
    except Exception as e:
        logger.error(f"Trim Error (fallback to slice): {e}")
        # Если trim_messages упал из-за нарушенной последовательности, берем последние сообщения вручную
        trimmed_messages = text_only_messages[-6:] if len(text_only_messages) > 6 else text_only_messages

    # 4. СБОРКА ИТОГОВОГО ПАКЕТА: Системный промпт идет первым
    final_messages = [SystemMessage(content=sys_content + format_instruction)]

    # Находим индекс последнего HumanMessage в уже ОБРЕЗАННОЙ истории
    last_human_idx = -1
    for i, msg in enumerate(trimmed_messages):
        if isinstance(msg, HumanMessage):
            last_human_idx = i

    # 5. ИНЖЕКЦИЯ ЧЕРТЕЖА: Клеим base64 ТОЛЬКО к последнему вопросу
    for i, msg in enumerate(trimmed_messages):
        if i == last_human_idx and state.get("current_drawing"):
            raw_b64 = state["current_drawing"]
            # Очищаем префиксы фронтенда, если они прилетели
            clean_b64 = raw_b64.split('base64,')[-1] if 'base64,' in raw_b64 else raw_b64
            
            multimodal_msg = HumanMessage(
                content=[
                    {"type": "text", "text": msg.content},
                    {
                        "type": "image_url", 
                        "image_url": {
                            "url": f"data:image/png;base64,{clean_b64}",
                            "detail": "high"  # Максимальное качество для распознавания мелких элементов чертежа
                        }
                    }
                ]
            )
            final_messages.append(multimodal_msg)
        else:
            final_messages.append(msg)

    # 6. ВЫЗОВ МОДЕЛИ
    try:
        response = await llm.ainvoke(
            final_messages, 
            max_tokens=cfg.agent.get('max_response_tokens', 2048)
        )
        return {"messages": [response]}
    except Exception as e:
        logger.error(f"LLM Invocation Error: {e}")
        return {"messages": [AIMessage(content="Ошибка при анализе чертежа. Пожалуйста, повторите запрос.")]}

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
