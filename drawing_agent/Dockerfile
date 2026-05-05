FROM python:3.12-slim

WORKDIR /app

# Системные либы для OpenCV и PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 poppler-utils curl \
    && rm -rf /var/lib/apt/lists/*

COPY drawing_agent/requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY drawing_agent/ .

# Создаем папки для кэша и логов, создаем пользователя и даем права
RUN mkdir -p logs dataset /app/.cache /app/.EasyOCR && useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# --- ПРЕДЗАГРУЗКА МОДЕЛЕЙ (чтобы не ждать при запросе) ---
# Скачиваем веса OCR и SentenceTransformer в слой образа как appuser
ENV HOME=/app
ENV HF_HOME=/app/.cache
ENV SENTENCE_TRANSFORMERS_HOME=/app/.cache
RUN python -c "import easyocr; easyocr.Reader(['ru', 'en'])" && \
    python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

EXPOSE 8000
ENV PYTHONPATH=/app

CMD ["python", "main.py"]