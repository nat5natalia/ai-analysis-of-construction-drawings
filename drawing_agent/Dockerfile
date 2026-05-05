FROM python:3.12-slim

WORKDIR /app

# Системные либы для OpenCV и PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY drawing_agent/requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# --- ПРЕДЗАГРУЗКА МОДЕЛЕЙ (чтобы не ждать при запросе) ---
# Скачиваем веса OCR и SentenceTransformer в слой образа
RUN python -c "import easyocr; easyocr.Reader(['ru', 'en'])" && \
    python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY drawing_agent/ .

# Создаем папки для кэша и логов и даем права
RUN mkdir -p logs dataset && useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
ENV PYTHONPATH=/app

CMD ["python", "main.py"]