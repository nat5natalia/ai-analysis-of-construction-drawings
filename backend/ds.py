import asyncio
from typing import Optional

# Глобальный агент или модель – инициализируем один раз
_agent = None

async def get_agent():
    """Ленивая инициализация агента (если он асинхронный)."""
    global _agent
    if _agent is None:
        _agent = await asyncio.to_thread(get_agent())
    return _agent

async def generate_description(image_path: str, metadata: Optional[str] = None) -> str:
    """
    Генерация описания чертежа.
    Предполагается, что сама модель синхронная (например, transformers).
    """
    agent = await get_agent()
    # Запускаем синхронную функцию в отдельном потоке, чтобы не блокировать event loop
    description = await asyncio.to_thread(
        agent.generate_description_sync, image_path, metadata
    )
    return description

async def answer_question(question: str, context: Optional[str] = None) -> str:
    agent = await get_agent()
    answer = await asyncio.to_thread(
        agent.answer_question_sync, question, context
    )
    return answer