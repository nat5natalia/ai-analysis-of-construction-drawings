FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 poppler-utils curl \
    && rm -rf /var/lib/apt/lists/*

COPY drawing_agent/requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY drawing_agent/ .

RUN mkdir -p logs dataset /app/.cache /app/.EasyOCR && \
    useradd -m appuser && \
    chown -R appuser:appuser /app

ENV HOME=/app
ENV HF_HOME=/app/.cache
ENV SENTENCE_TRANSFORMERS_HOME=/app/.cache
ENV YOLO_CONFIG_DIR=/tmp/Ultralytics
ENV PYTHONPATH=/app

RUN python -c "import easyocr; easyocr.Reader(['ru', 'en'])" && \
    python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

USER appuser

EXPOSE 8000
CMD ["python", "main.py"]