FROM python:3.12-slim

WORKDIR /app

# Системные зависимости для ML и работы с документами
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 poppler-utils \
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

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]