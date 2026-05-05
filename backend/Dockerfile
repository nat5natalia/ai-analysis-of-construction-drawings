FROM python:3.12-slim

WORKDIR /app

# Копируем зависимости
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем содержимое backend прямо в /app
COPY backend/ .

# Копируем воркер в подпапку, чтобы импорты 'from celery_worker' работали
COPY celery_worker/ ./celery_worker/

# Указываем Python, где искать модули
ENV PYTHONPATH=/app

EXPOSE 8000

# Так как main.py теперь лежит в корне /app, запускаем его так:
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]