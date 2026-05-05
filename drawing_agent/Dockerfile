FROM python:3.12-slim

WORKDIR /app

# Системные либы
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Обновляем pip и ставим зависимости одной группой
# Использование --no-cache-dir здесь критически важно
COPY drawing_agent/requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY drawing_agent/ .
EXPOSE 8000
ENV PYTHONPATH=/app

CMD ["python", "main.py"]