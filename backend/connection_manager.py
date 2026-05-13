import logging
from fastapi import WebSocket
from typing import Dict, List

# --- Инициализация логирования ---
# Мы настраиваем базовый логгер. Если этот файл импортируется в main.py,
# настройки подхватятся из основного приложения, но инициализация здесь
# гарантирует, что ошибки не возникнет.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("ConnectionManager")


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

        # ЛОГ: Позволяет увидеть, что фронтенд успешно открыл сокет для конкретного ID
        logger.info(
            f"Новое соединение WS. Drawing ID: {drawing_id}. Всего активных окон для этого ID: {len(self.active_connections[drawing_id])}")

    def disconnect(self, websocket: WebSocket, drawing_id: str):
        """Удаляет закрытое соединение из списка рассылки."""
        if drawing_id in self.active_connections:
            if websocket in self.active_connections[drawing_id]:
                self.active_connections[drawing_id].remove(websocket)
                # ЛОГ: Отслеживаем закрытие вкладок пользователем
                logger.info(
                    f"Соединение закрыто. Drawing ID: {drawing_id}. Осталось активных: {len(self.active_connections[drawing_id])}")

            if not self.active_connections[drawing_id]:
                del self.active_connections[drawing_id]
                logger.info(f" Все соединения для {drawing_id} закрыты. Ключ удален из памяти.")

    async def send_to_drawing(self, message: dict, drawing_id: str):
        """Отправляет JSON-данные всем, кто открыл конкретный чертеж."""
        if drawing_id in self.active_connections:
            connections = self.active_connections[drawing_id]

            # ЛОГ: Самый важный этап — подтверждение, что бэкенд видит получателей
            logger.info(f"Рассылка данных в WS для {drawing_id}. Получателей: {len(connections)}")

            for connection in connections:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    # ЛОГ: Если отправка не удалась (например, сокет внезапно оборвался)
                    logger.error(f"Ошибка при отправке в WS для {drawing_id}: {e}")
                    pass
        else:
            # ЛОГ: Если это сработает — значит сообщение от AI пришло, а слушателей (фронтенда) нет
            logger.warning(f"Сообщение для {drawing_id} пропущено: активных WebSocket-подписок не найдено.")


# Создаем один экземпляр на всё приложение
manager = ConnectionManager()