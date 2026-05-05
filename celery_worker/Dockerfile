FROM python:3.12-slim

WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Копируем файл зависимостей, указывая путь от корня проекта
COPY celery_worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем всё содержимое папки воркера в корень контейнера (/app)
COPY celery_worker/ .

# Также копируем общие модули (например, db.py), если они лежат в корне проекта
# COPY db.py .

ENV PYTHONPATH=/app

CMD ["celery", "-A", "worker", "worker", "--loglevel=info"]