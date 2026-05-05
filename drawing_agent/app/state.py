from typing import TypedDict, Annotated, List, Any, Optional, Dict
from omegaconf import DictConfig
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    # Annotated с add_messages критически важен для истории чата
    messages: Annotated[List[BaseMessage], add_messages]
    current_drawing: Optional[str]
    drawing_width: int
    drawing_height: int
    page: int
    ocr_text: str
    context: str
    tool_results: Dict[str, List[str]]
    extracted_holes: List[Dict]
    extracted_dimensions: Dict
    extracted_objects: List[Dict]
    text_dimensions: List[str]
    analysis_complete: bool
    yolo_detection: Dict[str, int]
    yolo_dimension_lines: str
    wait_time: int
    max_retries: int
    final_output: Optional[Dict[str, Any]]
    drawing_context: Optional[str]