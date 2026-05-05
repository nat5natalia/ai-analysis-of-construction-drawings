FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY celery_worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY celery_worker/ .

# Если нужен доступ к db.py из бэкенда, убедись что он копируется
# COPY backend/db.py ./db.py

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app

CMD ["celery", "-A", "worker", "worker", "--loglevel=info"]