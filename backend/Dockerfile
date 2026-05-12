FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 poppler-utils \
    gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем содержимое backend прямо в /app
COPY backend/ .

# Копируем воркер в подпапку для корректных импортов
COPY celery_worker/ ./celery_worker/

# Создаем пользователя для безопасности
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app
EXPOSE 8000

# Запускаем с одним воркером, чтобы ConnectionManager в памяти процесса
# корректно управлял WebSocket-соединениями без рассинхронизации.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]