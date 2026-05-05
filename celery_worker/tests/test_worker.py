import pytest
from unittest.mock import patch, MagicMock
from worker import process_drawing


@patch("worker.requests.post")
@patch("worker.drawings_collection")
def test_process_drawing_success(mock_db, mock_post):
    # Имитируем, что чертеж есть в базе
    mock_db.find_one.return_value = {"id": "123", "file_path": "/tmp/test.png"}

    # Имитируем успешный ответ Агента
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True, "answer": "Это чертеж здания"}
    mock_post.return_value = mock_response

    # Запускаем задачу (вызываем функцию напрямую без .delay())
    result = process_drawing("123", "Опиши этот чертеж")

    assert result["status"] == "completed"
    # Проверяем, что в БД ушло обновление с описанием
    mock_db.update_one.assert_called_once()
    args, kwargs = mock_db.update_one.call_args
    assert kwargs["$set"]["description"] == "Это чертеж здания"