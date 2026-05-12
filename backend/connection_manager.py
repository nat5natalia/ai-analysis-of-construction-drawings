from fastapi import WebSocket
from typing import Dict, List

class ConnectionManager:
    """
    Управляет активными WebSocket-соединениями.
    Позволяет рассылать сообщения по drawing_id.
    """
    def __init__(self):
        # Словарь вида { drawing_id: [список_сокетов] }
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, drawing_id: str):
        """Регистрирует новое соединение в системе."""
        await websocket.accept()
        if drawing_id not in self.active_connections:
            self.active_connections[drawing_id] = []
        self.active_connections[drawing_id].append(websocket)

    def disconnect(self, websocket: WebSocket, drawing_id: str):
        """Удаляет закрытое соединение из списка рассылки."""
        if drawing_id in self.active_connections:
            self.active_connections[drawing_id].remove(websocket)
            # Очищаем ключ, если в списке больше нет сокетов
            if not self.active_connections[drawing_id]:
                del self.active_connections[drawing_id]

    async def send_to_drawing(self, message: dict, drawing_id: str):
        """Отправляет JSON-данные всем, кто открыл конкретный чертеж."""
        if drawing_id in self.active_connections:
            for connection in self.active_connections[drawing_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    # Если сокет «протух», его стоит игнорировать
                    pass

# Создаем один экземпляр на всё приложение
manager = ConnectionManager()