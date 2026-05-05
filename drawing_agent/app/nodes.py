import time
import base64
import re
from io import BytesIO
from typing import Dict, List, Any
from PIL import Image
from omegaconf import DictConfig
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

from app.state import AgentState
from app.llm import get_llm
from app.tools import ALL_TOOLS
from app.monitoring import log_to_clearml
import logging
logger = logging.getLogger(__name__)

def preprocess_node(state: AgentState, cfg: DictConfig) -> AgentState:    
    if not state.get("current_drawing"):
        state["messages"].append(AIMessage(content=" Чертеж не загружен"))
        return state
    
    try:
        image_data = base64.b64decode(state["current_drawing"])
        img = Image.open(BytesIO(image_data))
        
        state["drawing_width"] = img.size[0]
        state["drawing_height"] = img.size[1]
        
        scale = cfg.image.scale if cfg and hasattr(cfg, 'image') else 0.1
        
        state['drawing_context'] = f"""Контекст чертежа:
- Размер изображения: {state['drawing_width']}×{state['drawing_height']} пикселей
- Масштаб: 1:{int(1/scale)} ({int(1/scale)} пикселей = 1 мм)"""
        
        state["messages"].insert(0, AIMessage(content=state['drawing_context']))
        state["analysis_complete"] = True
        logger.info(f"Чертеж загружен: {state['drawing_width']}x{state['drawing_height']}")
        log_to_clearml(f"Чертеж загружен: {state['drawing_width']}x{state['drawing_height']}")
        
    except Exception as e:
        state["messages"].append(AIMessage(content=f"Ошибка загрузки: {e}"))
    
    return state


def agent_node(state: AgentState, cfg: DictConfig) -> AgentState:
    llm = get_llm(cfg)
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
                messages[i] = HumanMessage(
                    content=[
                        {"type": "text", "text": msg.content},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{clean_b64}"}}
                    ]
                )
                break
    wait_time = state.get('wait_time', cfg.agent.wait_time if cfg and hasattr(cfg, 'agent') else 4)
    time.sleep(wait_time)
    last_question = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            last_question = msg.content[:200]
            break
    log_to_clearml(f"Вопрос: {last_question}")
    try:
        llm_with_tools = llm.bind_tools(ALL_TOOLS)
        response = llm_with_tools.invoke(messages)
        state["messages"].append(response)
        log_to_clearml(f"Ответ получен: {len(response.content)} символов")
    except Exception as e:
        error_msg = str(e)
        state["messages"].append(AIMessage(content=f"Ошибка: {error_msg}"))
        logger.error(f'Ошибка: {error_msg[:200]}')
        log_to_clearml(f"Ошибка: {error_msg[:200]}")
    
    return state


def tools_node(state: AgentState) -> AgentState:    
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
                result = tool.invoke(tool_args)
            else:
                result = f"Неизвестный инструмент: {tool_name}"
            
            tool_results.append(
                ToolMessage(content=str(result), tool_call_id=tool_call.get("id", ""))
            )
            
            if tool_name not in state["tool_results"]:
                state["tool_results"][tool_name] = []
            state["tool_results"][tool_name].append(str(result))
            if tool_name == "extract_text":
                state["ocr_text"] = result
            elif tool_name == "detect_holes":
                state["extracted_holes"] = _parse_holes_result(result)
            elif tool_name == "extract_dimensions":
                state["extracted_dimensions"] = _parse_dimensions_result(result)
            elif tool_name == "detect_tables":
                if "extracted_tables" not in state:
                    state["extracted_tables"] = []
                state["extracted_tables"].append(result)
            elif tool_name == "extract_dims":
                if "text_dimensions" not in state:
                    state["text_dimensions"] = []
                state["text_dimensions"].append(result)
            elif tool_name == "detect_objects":
                state["extracted_objects"] = _parse_objects_result(result)
            elif tool_name == "get_drawing_metadata":
                state["metadata_retrieved"] = True
            elif tool_name == "detect_yolo_objects":
                state["yolo_detection"] = _parse_yolo_result(result)
            elif tool_name == "find_dimension_lines":
                state["yolo_dimension_lines"] = result
        except Exception as e:
            error_msg = f"Ошибка при вызове {tool_name}: {str(e)}"
            tool_results.append(
                ToolMessage(content=error_msg, tool_call_id=tool_call.get("id", ""))
            )
            logger.error(error_msg)
            log_to_clearml(error_msg)
            if tool_name not in state["tool_results"]:
                state["tool_results"][tool_name] = []
            state["tool_results"][tool_name].append(f"ERROR: {error_msg}")
    state["messages"].extend(tool_results)
    return state

def instructor_node(state: AgentState, cfg: DictConfig) -> AgentState:
    use_instructor = cfg.run.get('use_instructor', True) if cfg and hasattr(cfg, 'run') else True
    if not use_instructor:
        return state
    try:
        from app.instructor.client import get_instructor_client
        from app.instructor.extractor import run_instructor
        from app.instructor.schemas import DrawingAnalysis
        client = get_instructor_client()
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

    # Если модель хочет вызвать инструменты — идем в tools
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    # Если инструментов нет, проверяем флаг инструктора
    use_instructor = cfg.run.get('use_instructor', True) if cfg and hasattr(cfg, 'run') else True

    # Важно: идем в инструктор только если анализ завершен и нет вызовов инструментов
    if use_instructor and state.get("analysis_complete"):
        return "instructor"

    return "__end__"

def _parse_holes_result(result: str) -> List[Dict]:
    holes = []
    if not result or "Отверстия не обнаружены" in result:
        return holes
    if "Обнаружено отверстий:" in result:
        lines = result.split('\n')
        for line in lines:
            match = re.search(r'Отверстие \d+: центр \((\d+), (\d+)\), радиус (\d+)', line)
            if match:
                holes.append({
                    "center_x": int(match.group(1)),
                    "center_y": int(match.group(2)),
                    "radius_px": int(match.group(3))
                })
    
    return holes

def _parse_dimensions_result(result: str) -> Dict:
    dimensions = {
        "width_mm": None,
        "height_mm": None,
        "lines_count": None,
        "raw": result
    }
    if not result:
        return dimensions
    width_match = re.search(r'Ширина:\s+([\d\.]+)\s+мм', result)
    if width_match:
        dimensions["width_mm"] = float(width_match.group(1))
    height_match = re.search(r'Высота:\s+([\d\.]+)\s+мм', result)
    if height_match:
        dimensions["height_mm"] = float(height_match.group(1))
    lines_match = re.search(r'Количество линий:\s+(\d+)', result)
    if lines_match:
        dimensions["lines_count"] = int(lines_match.group(1))
    return dimensions

def _parse_objects_result(result: str) -> List[str]:
    objects = []
    if not result:
        return objects
    if "Обнаруженные объекты:" in result:
        objects_str = result.split("Обнаруженные объекты:")[1].strip()
        objects = [obj.strip() for obj in objects_str.split(',')]
    elif "Объекты не обнаружены" not in result:
        for keyword in ["отверстия", "размеры", "линии", "таблицы", "обозначения"]:
            if keyword in result.lower():
                objects.append(keyword)
    
    return objects

def _parse_yolo_result(result: str) -> Dict:
    import re
    parsed = {
        "dimension_lines": 0,
        "tables": 0,
        "text_blocks": 0,
        "symbols": 0,
        "raw": result
    }
    lines_match = re.search(r'Размерные линии: (\d+)', result)
    if lines_match:
        parsed["dimension_lines"] = int(lines_match.group(1))
    tables_match = re.search(r'Таблицы: (\d+)', result)
    if tables_match:
        parsed["tables"] = int(tables_match.group(1))
    text_match = re.search(r'Текстовые блоки: (\d+)', result)
    if text_match:
        parsed["text_blocks"] = int(text_match.group(1))
    symbols_match = re.search(r'Символы: (\d+)', result)
    if symbols_match:
        parsed["symbols"] = int(symbols_match.group(1))
    return parsed

def get_tool_results_summary(state: AgentState) -> str:
    summary = []
    if "tool_results" not in state:
        return "Нет результатов инструментов"
    for tool_name, results in state["tool_results"].items():
        summary.append(f"{tool_name}: {len(results)} вызовов")
    return "\n".join(summary)