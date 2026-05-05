import asyncio
import base64
import re
import logging
from io import BytesIO
from typing import Dict, List, Any
from PIL import Image
from omegaconf import DictConfig
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

from app.state import AgentState
from app.llm import get_llm
from app.tools import ALL_TOOLS
from app.monitoring import log_to_clearml

logger = logging.getLogger(__name__)


async def preprocess_node(state: AgentState, cfg: DictConfig) -> AgentState:
    if not state.get("current_drawing"):
        state["messages"].append(AIMessage(content="Чертеж не загружен"))
        return state

    try:
        # Декодирование base64
        image_data = base64.b64decode(state["current_drawing"])
        img = Image.open(BytesIO(image_data))

        state["drawing_width"] = img.size[0]
        state["drawing_height"] = img.size[1]

        scale = cfg.image.scale if cfg and hasattr(cfg, 'image') else 0.1

        state['drawing_context'] = f"""Контекст чертежа:
- Размер изображения: {state['drawing_width']}×{state['drawing_height']} пикселей
- Масштаб: 1:{int(1 / scale)} ({int(1 / scale)} пикселей = 1 мм)"""

        state["messages"].insert(0, AIMessage(content=state['drawing_context']))
        state["analysis_complete"] = True
        logger.info(f"Чертеж загружен: {state['drawing_width']}x{state['drawing_height']}")
        log_to_clearml(f"Чертеж загружен: {state['drawing_width']}x{state['drawing_height']}")

    except Exception as e:
        state["messages"].append(AIMessage(content=f"Ошибка загрузки: {e}"))

    return state


async def agent_node(state: AgentState, cfg: DictConfig) -> AgentState:
    llm = get_llm(cfg)
    system_prompt = ""
    if cfg and hasattr(cfg, 'agent') and hasattr(cfg.agent, 'system_prompt'):
        system_prompt = cfg.agent.system_prompt

    if state.get('drawing_context'):
        system_prompt += f"\n\n{state['drawing_context']}"
    if state.get("context"):
        system_prompt += f"\n\nДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ:\n{state['context']}"
    if state.get("ocr_text"):
        system_prompt += f"\n\nРАСПОЗНАННЫЙ ТЕКСТ:\n{state['ocr_text']}"

    messages = [SystemMessage(content=system_prompt)]
    for msg in state["messages"]:
        messages.append(msg)

    current_drawing = state.get("current_drawing")
    if current_drawing:
        clean_b64 = current_drawing
        if 'base64,' in clean_b64:
            clean_b64 = clean_b64.split('base64,')[-1]

        for i, msg in enumerate(messages):
            if isinstance(msg, HumanMessage):
                # Подготовка контента с текстом и картинкой
                text_content = msg.content if isinstance(msg.content, str) else ""
                messages[i] = HumanMessage(
                    content=[
                        {"type": "text", "text": text_content},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{clean_b64}"}}
                    ]
                )
                break

    wait_time = state.get('wait_time', cfg.agent.wait_time if cfg and hasattr(cfg, 'agent') else 4)
    # Использование асинхронной задержки вместо time.sleep
    await asyncio.sleep(wait_time)

    last_question = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            last_question = msg.content[:200] if isinstance(msg.content, str) else "Image question"
            break

    log_to_clearml(f"Вопрос: {last_question}")

    try:
        llm_with_tools = llm.bind_tools(ALL_TOOLS)
        # КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: использование ainvoke
        response = await llm_with_tools.ainvoke(messages)
        state["messages"].append(response)
        log_to_clearml(f"Ответ получен: {len(response.content)} символов")
    except Exception as e:
        error_msg = str(e)
        state["messages"].append(AIMessage(content=f"Ошибка LLM: {error_msg}"))
        logger.error(f'Ошибка: {error_msg}')
        log_to_clearml(f"Ошибка: {error_msg[:200]}")

    return state


async def tools_node(state: AgentState) -> AgentState:
    messages = state["messages"]
    last_message = messages[-1]

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return state

    tool_results = []
    if "tool_results" not in state:
        state["tool_results"] = {}

    for tool_call in last_message.tool_calls:
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args", {})

        log_to_clearml(f"Вызов инструмента: {tool_name}")
        logger.info(f'Вызов инструмента {tool_name}')

        try:
            tool = next((t for t in ALL_TOOLS if t.name == tool_name), None)

            if tool:
                # Пытаемся вызвать асинхронно, если инструмент поддерживает
                if hasattr(tool, "ainvoke"):
                    result = await tool.ainvoke(tool_args)
                else:
                    result = tool.invoke(tool_args)
            else:
                result = f"Неизвестный инструмент: {tool_name}"

            tool_results.append(
                ToolMessage(content=str(result), tool_call_id=tool_call.get("id", ""))
            )

            if tool_name not in state["tool_results"]:
                state["tool_results"][tool_name] = []
            state["tool_results"][tool_name].append(str(result))

            # Обновление стейта на основе вызовов
            if tool_name == "extract_text":
                state["ocr_text"] = result
            elif tool_name == "detect_holes":
                state["extracted_holes"] = _parse_holes_result(str(result))
            elif tool_name == "extract_dimensions":
                state["extracted_dimensions"] = _parse_dimensions_result(str(result))
            elif tool_name == "detect_tables":
                if "extracted_tables" not in state:
                    state["extracted_tables"] = []
                state["extracted_tables"].append(result)
            elif tool_name == "detect_yolo_objects":
                state["yolo_detection"] = _parse_yolo_result(str(result))

        except Exception as e:
            error_msg = f"Ошибка при вызове {tool_name}: {str(e)}"
            tool_results.append(
                ToolMessage(content=error_msg, tool_call_id=tool_call.get("id", ""))
            )
            logger.error(error_msg)
            log_to_clearml(error_msg)

    state["messages"].extend(tool_results)
    return state


async def instructor_node(state: AgentState, cfg: DictConfig) -> AgentState:
    use_instructor = cfg.run.get('use_instructor', True) if cfg and hasattr(cfg, 'run') else True
    if not use_instructor:
        return state
    try:
        from app.instructor.client import get_instructor_client
        from app.instructor.extractor import run_instructor
        from app.instructor.schemas import DrawingAnalysis

        client = get_instructor_client()
        # Если run_instructor синхронная, можно оставить так,
        # но лучше обернуть в run_in_executor если она тяжелая
        result = run_instructor(client, state, DrawingAnalysis)
        state["final_output"] = result.dict() if result else None

        logger.info('Instructor структурировал ответ')
        log_to_clearml("Instructor структурировал ответ")
    except Exception as e:
        logger.error(f'Instructor ошибка: {str(e)}')
        log_to_clearml(f"Instructor ошибка: {str(e)}")

    return state


def should_continue(state: AgentState, cfg: DictConfig):
    messages = state["messages"]
    if not messages:
        return "__end__"

    last_message = messages[-1]

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    use_instructor = cfg.run.get('use_instructor', True) if cfg and hasattr(cfg, 'run') else True

    if use_instructor and state.get("analysis_complete"):
        return "instructor"

    return "__end__"


# --- Хелперы парсинга ---

def _parse_holes_result(result: str) -> List[Dict]:
    holes = []
    if not result or "Отверстия не обнаружены" in result:
        return holes

    matches = re.finditer(r'Отверстие \d+: центр \((\d+), (\d+)\), радиус (\d+)', result)
    for match in matches:
        holes.append({
            "center_x": int(match.group(1)),
            "center_y": int(match.group(2)),
            "radius_px": int(match.group(3))
        })
    return holes


def _parse_dimensions_result(result: str) -> Dict:
    dimensions = {"width_mm": None, "height_mm": None, "lines_count": None, "raw": result}
    if not result:
        return dimensions

    w = re.search(r'Ширина:\s+([\d\.]+)\s+мм', result)
    h = re.search(r'Высота:\s+([\d\.]+)\s+мм', result)
    l = re.search(r'Количество линий:\s+(\d+)', result)

    if w: dimensions["width_mm"] = float(w.group(1))
    if h: dimensions["height_mm"] = float(h.group(1))
    if l: dimensions["lines_count"] = int(l.group(1))
    return dimensions


def _parse_yolo_result(result: str) -> Dict:
    parsed = {"dimension_lines": 0, "tables": 0, "text_blocks": 0, "symbols": 0, "raw": result}

    patterns = {
        "dimension_lines": r'Размерные линии: (\d+)',
        "tables": r'Таблицы: (\d+)',
        "text_blocks": r'Текстовые блоки: (\d+)',
        "symbols": r'Символы: (\d+)'
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, result)
        if match:
            parsed[key] = int(match.group(1))
    return parsed


def get_tool_results_summary(state: AgentState) -> str:
    if "tool_results" not in state or not state["tool_results"]:
        return "Нет результатов инструментов"

    summary = []
    for tool_name, results in state["tool_results"].items():
        summary.append(f"{tool_name}: {len(results)} вызовов")
    return "\n".join(summary)