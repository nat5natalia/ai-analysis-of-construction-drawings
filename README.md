# AI анализ строительных чертежей

Система для загрузки, просмотра и интеллектуального анализа строительных чертежей. Проект принимает PDF и изображения, строит техническое описание, отвечает на вопросы по документу, ищет чертежи по тексту и хранит историю обработки.

## Оглавление

- [Состав проекта](#состав-проекта)
- [Архитектура](#архитектура)
- [Требования](#требования)
- [Переменные окружения](#переменные-окружения)
- [Запуск на CPU](#запуск-на-cpu)
- [Запуск на GPU](#запуск-на-gpu)
- [Локальная разработка без полного Docker-запуска](#локальная-разработка-без-полного-docker-запуска)
- [API](#api)
- [Модели и данные](#модели-и-данные)
- [Тесты](#тесты)
- [Полезные команды](#полезные-команды)

## Состав проекта

- `frontend` - интерфейс на React, Vite, TypeScript, Redux Toolkit и Tailwind CSS.
- `backend` - FastAPI-сервис для загрузки файлов, выдачи данных фронтенду, WebSocket-обновлений и работы с MongoDB.
- `celery_worker` - Celery-воркер, который забирает задачи из Redis, вызывает ИИ-агента и обновляет MongoDB.
- `drawing_agent` - FastAPI-сервис ИИ-агента: OCR, обработка изображений, YOLO, FAISS/RAG, LangGraph и обращение к OpenAI-совместимому LLM API.
- `dataset` - локальная папка с загруженными PDF и изображениями.
- `persistent_storage` - постоянное хранилище FAISS-индекса, метаданных и кеша агента.
- `drawing_agent/models` - локальные модели EasyOCR, Sentence Transformers и YOLO (`best.pt`).

## Архитектура

```text
frontend (localhost:3000)
    |
    | HTTP / WebSocket
    v
backend (localhost:8000)
    |
    | Celery task
    v
Redis + celery_worker
    |
    | HTTP внутри Docker-сети
    v
drawing_agent (drawing_agent:8000)
    |
    +-- MongoDB: метаданные, статусы, история сообщений
    +-- PostgreSQL: checkpoint-хранилище LangGraph
    +-- persistent_storage: FAISS-индекс и кеш
    +-- dataset: исходные PDF/изображения
```

Основной сценарий:

1. Пользователь загружает чертеж во фронтенде.
2. `backend` сохраняет файл в `dataset`, создаёт запись в MongoDB и ставит задачу в Celery.
3. `celery_worker` ждёт готовности `drawing_agent` и вызывает `/pre-analyze`, затем `/process`.
4. `drawing_agent` выполняет OCR, извлечение признаков, анализ через LLM и обновляет локальный FAISS-индекс.
5. `backend` получает уведомления через Redis Pub/Sub и отправляет обновления во фронтенд через WebSocket.

## Требования

- Docker и Docker Compose.
- Для CPU-запуска достаточно обычного Docker.
- Для GPU-запуска нужны NVIDIA-драйвер, NVIDIA Container Toolkit и видеокарта с поддержкой CUDA.
- Ключ для OpenAI-совместимого LLM API в переменной `OPENAI_API_KEY`.

## Переменные окружения

Создайте `.env` в корне проекта. Можно начать с копии `.env.example`:

```powershell
Copy-Item .env.example .env
```

При Docker-запуске Compose читает этот файл как источник переменных для build args, device-настроек и Docker secret. Значение `OPENAI_API_KEY` не передаётся в `drawing_agent` обычной environment-переменной: оно монтируется как secret-файл `/run/secrets/openai_api_key`, а приложение читает путь из `OPENAI_API_KEY_FILE`.

Минимальный вариант для CPU:

```env
OPENAI_API_KEY=your_openai_api_key_here
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/langgraph_db
AGENT_DEVICE=cpu
TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
```

Важные переменные:

- `OPENAI_API_KEY` - обязательный ключ для обращения к LLM.
- `OPENAI_API_KEY_FILE` - внутренний путь к Docker secret внутри контейнера `drawing_agent`; вручную в `.env` обычно не задаётся.
- `DATABASE_URL` - адрес PostgreSQL для checkpoint-хранилища LangGraph. В Docker Compose по умолчанию используется `postgresql://postgres:postgres@postgres:5432/langgraph_db`.
- `AGENT_DEVICE` - устройство для `drawing_agent`: `cpu`, `cuda` или `auto`.
- `TORCH_INDEX_URL` - индекс PyTorch при сборке образа `drawing_agent`.
- `CELERY_CONCURRENCY` - число процессов Celery. Если не задано, используется `1`.

В `docker-compose.yml` Redis, MongoDB, PostgreSQL, `AGENT_URL`, `DATASET_PATH` и внутренние адреса сервисов уже заданы. Обычно их не нужно прописывать в `.env` для Docker-запуска.

Не используйте `docker compose config` для публикации логов или скриншотов без фильтрации: команда безопаснее после перехода на secret, но всё равно раскрывает структуру секретов и локальные пути.

## Запуск на CPU

CPU-режим подходит для локальной разработки и машин без NVIDIA GPU.

1. Подготовьте `.env`:

```env
OPENAI_API_KEY=your_openai_api_key_here
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/langgraph_db
AGENT_DEVICE=cpu
TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
```

2. Соберите и запустите сервисы:

```powershell
docker compose up --build -d
```

После старта Compose поднимает Redis, MongoDB, PostgreSQL, `drawing_agent`, `celery-worker`, `backend` и `frontend`. Backend ждёт готовности агента, Redis и MongoDB, а worker дополнительно ждёт PostgreSQL.

3. Откройте приложение:

- фронтенд: `http://localhost:3000`
- backend API: `http://localhost:8000`
- Swagger backend: `http://localhost:8000/docs`

Полезные команды:

```powershell
docker compose ps
docker compose logs -f drawing_agent
docker compose logs -f backend
docker compose logs -f celery-worker
```

Остановка:

```powershell
docker compose down
```

Остановка с удалением Docker-томов MongoDB и PostgreSQL:

```powershell
docker compose down -v
```

Папки `dataset` и `persistent_storage` подключены как bind mount из рабочей директории, поэтому `docker compose down -v` не удаляет их содержимое автоматически.

## Запуск на GPU

GPU-режим ускоряет части пайплайна, которые используют PyTorch/CUDA. В проекте для этого есть override-файл `docker-compose.gpu.yml`.

1. Проверьте, что Docker видит видеокарту:

```powershell
docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi
```

2. Подготовьте `.env`:

```env
OPENAI_API_KEY=your_openai_api_key_here
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/langgraph_db
AGENT_DEVICE=cuda
TORCH_INDEX_URL=https://download.pytorch.org/whl/cu121
```

Можно оставить `AGENT_DEVICE=auto`: агент сам выберет `cuda`, если `torch.cuda.is_available()` вернёт `true`. Если указать `AGENT_DEVICE=cuda`, сервис упадёт при старте, если CUDA недоступна. Это удобно для явной проверки GPU-конфигурации.

3. Запустите проект с GPU override:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
```

`docker-compose.gpu.yml` добавляет `drawing_agent` доступ к NVIDIA GPU через `gpus: all`, прокидывает `NVIDIA_VISIBLE_DEVICES=all` и меняет дефолтный PyTorch index на CUDA 12.1.

Проверить логи агента:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml logs -f drawing_agent
```

Вернуться с GPU на CPU:

```env
AGENT_DEVICE=cpu
TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
```

После смены CPU/GPU индекса пересоберите образ агента, чтобы PyTorch был установлен из нужного index:

```powershell
docker compose build --no-cache drawing_agent
docker compose up
```

## Локальная разработка без полного Docker-запуска

Самый надёжный режим разработки - запускать весь стек через Docker Compose. Ручной запуск отдельных сервисов полезен для отладки, но требует уже поднятых Redis, MongoDB, PostgreSQL и корректных адресов сервисов.

Фронтенд:

```powershell
cd frontend
npm install
npm run dev
```

Vite проксирует `/api` и `/ws` на `http://127.0.0.1:8000`, поэтому локально backend должен быть доступен на порту `8000`.

Backend при уже поднятых Redis, MongoDB и агенте. В примере backend запускается на `8001`, потому что локальный `drawing_agent` по умолчанию занимает `8000`:

Если вы хотите запускать frontend через `npm run dev` без изменения `frontend/vite.config.ts`, backend должен слушать `8000`. Если одновременно локально запущен `drawing_agent` на `8000`, разведите порты и временно поменяйте Vite proxy на порт backend.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:MONGO_URL="mongodb://localhost:27017"
$env:REDIS_URL="redis://localhost:6379/0"
$env:AGENT_URL="http://localhost:8000"
$env:DATASET_PATH="../dataset"
uvicorn main:app --host 0.0.0.0 --port 8001 --workers 1
```

Агент при уже поднятом PostgreSQL:

```powershell
cd drawing_agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
$env:OPENAI_API_KEY="your_openai_api_key_here"
$env:AGENT_DEVICE="cpu"
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/langgraph_db"
python main.py
```

По умолчанию `drawing_agent/main.py` запускает агент на `8000`, а Vite-прокси фронтенда смотрит на backend `http://127.0.0.1:8000`. Для полностью ручного запуска нужно развести порты и при необходимости временно изменить target в `frontend/vite.config.ts`. В Docker Compose конфликта нет: наружу опубликован только backend `8000`, а агент доступен внутри Docker-сети как `http://drawing_agent:8000`.

## API

Основные endpoint'ы backend:

- `GET /api/drawings` - список чертежей.
- `GET /api/drawings/{drawing_id}` - данные одного чертежа.
- `POST /api/upload` - загрузка PDF или изображения.
- `POST /api/ask/{drawing_id}` - вопрос по чертежу.
- `GET /api/search?q=...` - поиск по чертежам.
- `DELETE /api/drawings/{drawing_id}` - удаление чертежа и кеша.
- `WS /ws/{drawing_id}` - обновления статуса и новые сообщения.

Основные endpoint'ы `drawing_agent` внутри Docker-сети:

- `GET /health` - базовая проверка.
- `GET /ready` - готовность агента к новой тяжёлой задаче.
- `POST /pre-analyze` - предварительный анализ и индексация.
- `POST /process` - ответ на вопрос по чертежу.
- `GET /api/search?q=...` - поиск по локальному FAISS-индексу.
- `POST /search` - совместимый endpoint поиска.
- `DELETE /cache/{drawing_id}` - удаление векторного кеша чертежа.

## Модели и данные

В репозитории ожидаются локальные модели:

- `drawing_agent/models/best.pt` - YOLO-модель для детекции элементов чертежа.
- `drawing_agent/models/easyocr` - модели EasyOCR.
- `drawing_agent/models/transformers/all-MiniLM-L6-v2` - Sentence Transformers для эмбеддингов.

Контейнер `drawing_agent` работает в offline-режиме для Hugging Face:

```env
TRANSFORMERS_OFFLINE=1
HF_DATASETS_OFFLINE=1
HF_HOME=/app/models/transformers
```

Если моделей нет, подготовьте их скриптом:

```powershell
cd drawing_agent
python download_models.py
```

Скрипту нужен доступ в интернет. После загрузки модели должны лежать в `drawing_agent/models`.

## Тесты

В проекте есть тесты для `backend`, `celery_worker` и `drawing_agent`:

```powershell
cd backend
pytest

cd ..\celery_worker
pytest

cd ..\drawing_agent
pytest
```

Часть тестов может требовать Redis, MongoDB, PostgreSQL, локальные модели и корректные переменные окружения.

## Полезные команды

Пересобрать только ИИ-агента:

```powershell
docker compose build drawing_agent
docker compose up drawing_agent
```

Посмотреть логи всех сервисов:

```powershell
docker compose logs -f
```

Посмотреть логи конкретного сервиса:

```powershell
docker compose logs -f drawing_agent
```

Очистить Docker-тома MongoDB/PostgreSQL и начать с пустой базы:

```powershell
docker compose down -v
```
