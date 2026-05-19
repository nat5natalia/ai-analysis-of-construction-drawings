FROM python:3.12-slim

WORKDIR /app

# 1. Системные зависимости (добавлен git на случай подтягивания пакетов)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 poppler-utils curl git \
    && rm -rf /var/lib/apt/lists/*

# 2. Обновляем pip
RUN pip install --no-cache-dir --upgrade pip

# 3. Установка чистого CPU PyTorch (Вот здесь магия скорости)
# ДЛЯ ЛОКАЛЬНОГО CPU ЗАПУСКА:
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# (Когда будете деплоить на GPU-сервер, просто замените строку выше на:
# RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu121)

# 4. Установка Ultralytics (он увидит готовый CPU-torch и не будет качать CUDA)
RUN pip install --no-cache-dir "ultralytics>=8.2.0"

# 5. Установка остальных зависимостей из requirements.txt
COPY drawing_agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. КОПИРУЕМ ВСЁ (Код и модели)
COPY drawing_agent/ .

# 7. Настройка прав
RUN mkdir -p logs dataset persistent_storage /app/models && \
    useradd -m appuser && \
    chown -R appuser:appuser /app

# 8. Оффлайн-конфиг
ENV PYTHONPATH=/app
ENV HF_HOME=/app/models/transformers
ENV SENTENCE_TRANSFORMERS_HOME=/app/models/transformers
ENV EASYOCR_MODULE_PATH=/app/models/easyocr
ENV TRANSFORMERS_OFFLINE=1
ENV HF_DATASETS_OFFLINE=1

USER appuser
EXPOSE 8000

CMD ["python", "main.py"]