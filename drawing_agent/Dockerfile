FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH="/app/backend:${PYTHONPATH}"
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# 1. PyTorch CPU (лёгкая версия)
RUN pip install --no-cache-dir --default-timeout=300 --retries 5 \
    torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu

# 2. Копируем и обрабатываем requirements.txt
COPY requirements.txt .
# На всякий случай удаляем строки с torch/torchvision (мало ли что)
RUN sed -i '/^torch/d; /^torchvision/d' requirements.txt
RUN pip install --no-cache-dir --default-timeout=300 --retries 5 -r requirements.txt

COPY . .

CMD ["python", "main.py"]