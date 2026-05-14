FROM python:3.12-slim

WORKDIR /app

# 1. Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 poppler-utils curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Установка библиотек (используем относительный путь .)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 3. КОПИРУЕМ ВСЁ (Код и модели уже должны быть в drawing_agent/)
# Точка копирует всё содержимое папки drawing_agent в /app
COPY . .

# 4. Настройка прав (после копирования!)
RUN mkdir -p logs dataset persistent_storage /app/models && \
    useradd -m appuser && \
    chown -R appuser:appuser /app

# 5. Оффлайн-конфиг
ENV PYTHONPATH=/app
ENV HF_HOME=/app/models/transformers
ENV SENTENCE_TRANSFORMERS_HOME=/app/models/transformers
ENV EASYOCR_MODULE_PATH=/app/models/easyocr
ENV TRANSFORMERS_OFFLINE=1
ENV HF_DATASETS_OFFLINE=1

USER appuser
EXPOSE 8000
CMD ["python", "main.py"]