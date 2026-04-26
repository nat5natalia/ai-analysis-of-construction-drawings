
import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
AGENT_PATH = Path(__file__).parent.parent / "agent"
sys.path.insert(0, str(AGENT_PATH))

from omegaconf import OmegaConf
from app.agent import DrawingAgent
from app.tools import set_current_drawing
import numpy as np
import base64
from io import BytesIO
from PIL import Image

_agent = None

def get_agent():
    global _agent
    if _agent is None:
        cfg = OmegaConf.load(AGENT_PATH / "config" / "config.yaml")
        _agent = DrawingAgent(cfg)
    return _agent


async def generate_description_async(image_base64: str) -> str:
    try:
        agent = get_agent()
        temp_path = AGENT_PATH / "temp_image.png"
        image_data = base64.b64decode(image_base64)
        with open(temp_path, "wb") as f:
            f.write(image_data)
        result = await agent.run(
            path=str(temp_path),
            question="Опиши подробно что изображено на этом строительном чертеже. Укажи размеры, элементы, особенности."
        )
        temp_path.unlink(missing_ok=True)
        if result["success"]:
            return result["answer"]
        else:
            return f"Ошибка генерации описания: {result['error']}"
    except Exception as e:
        return f"Ошибка: {str(e)}"


async def answer_question_async(image_base64: str, question: str) -> str:
    try:
        agent = get_agent()
        temp_path = AGENT_PATH / "temp_image.png"
        image_data = base64.b64decode(image_base64)
        with open(temp_path, "wb") as f:
            f.write(image_data)
        result = await agent.run(str(temp_path), question)
        temp_path.unlink(missing_ok=True)
        if result["success"]:
            return result["answer"]
        else:
            return f"Ошибка: {result['error']}"
    except Exception as e:
        return f"Ошибка: {str(e)}"

def compute_embedding(text: str) -> List[float]:
    if not hasattr(compute_embedding, "_model"):
        compute_embedding._model = SentenceTransformer('all-MiniLM-L6-v2')
    embedding = compute_embedding._model.encode(text)
    return embedding.tolist()

def generate_description(image_base64: str) -> str:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(generate_description_async(image_base64))
    finally:
        loop.close()

def answer_question(image_base64: str, question: str) -> str:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(answer_question_async(image_base64, question))
    finally:
        loop.close()