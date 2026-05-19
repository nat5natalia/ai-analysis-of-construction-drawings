# ROADMAP проекта "AI анализ строительных чертежей"

Документ описывает, что уже реализовано в проекте, и даёт примерную недельную реконструкцию того, как работа могла распределяться в период с 23 марта по 20 апреля.

## Оглавление

- [Что сделано](#что-сделано)
  - [Общая архитектура](#общая-архитектура)
  - [Frontend](#frontend)
  - [Backend](#backend)
  - [Celery worker](#celery-worker)
  - [Drawing Agent](#drawing-agent)
  - [Docker и запуск](#docker-и-запуск)
  - [Конфигурация и безопасность](#конфигурация-и-безопасность)
  - [Документация](#документация)
- [Примерная недельная хронология работ](#примерная-недельная-хронология-работ)
  - [23-29 марта](#23-29-марта)
  - [30 марта - 5 апреля](#30-марта---5-апреля)
  - [6-12 апреля](#6-12-апреля)
  - [13-20 апреля](#13-20-апреля)
  - [Работы, завершённые после базового недельного этапа](#работы-завершённые-после-базового-недельного-этапа)

## Что сделано

### Общая архитектура

- Собран интегрированный стек для анализа строительных чертежей.
- Проект разделён на независимые сервисы: `frontend`, `backend`, `celery_worker`, `drawing_agent`.
- Добавлены инфраструктурные сервисы: Redis, MongoDB и PostgreSQL.
- Настроен Docker Compose для локального запуска всей системы.
- Добавлен отдельный GPU override через `docker-compose.gpu.yml`.

### Frontend

- Реализован интерфейс на React, Vite, TypeScript и Redux Toolkit Query.
- Добавлены основные пользовательские сценарии:
  - список чертежей;
  - загрузка PDF/изображений;
  - просмотр карточки чертежа;
  - чат по выбранному чертежу;
  - поиск по коллекции;
  - удаление чертежа.
- Настроены запросы к backend API.
- Добавлена работа с WebSocket-обновлениями.
- Настроен dev proxy Vite для `/api` и `/ws`.
- Подготовлена production-сборка через nginx.

### Backend

- Реализован FastAPI backend.
- Добавлены endpoint'ы:
  - `GET /api/drawings`;
  - `GET /api/drawings/{drawing_id}`;
  - `POST /api/upload`;
  - `POST /api/ask/{drawing_id}`;
  - `GET /api/search`;
  - `DELETE /api/drawings/{drawing_id}`;
  - `WS /ws/{drawing_id}`.
- Добавлена загрузка PDF и изображений.
- Файлы сохраняются в `dataset`.
- Метаданные, статусы, описание и история сообщений сохраняются в MongoDB.
- Добавлена проверка повторной загрузки одинакового файла через SHA-256.
- Реализована передача статусов и ответов во frontend через Redis Pub/Sub и WebSocket.
- Добавлено извлечение упоминаний строительных стандартов из описаний и ответов.

### Celery worker

- Реализован Celery worker для фоновой обработки.
- Redis используется как broker/backend.
- Воркер получает задачу анализа, ждёт готовности `drawing_agent`, вызывает `/pre-analyze` и `/process`.
- Результаты записываются в MongoDB.
- Статусы обработки публикуются в Redis Pub/Sub.
- Добавлена настройка параллельности через `CELERY_CONCURRENCY`.

### Drawing Agent

- Реализован отдельный FastAPI-сервис `drawing_agent`.
- Добавлены endpoint'ы:
  - `GET /health`;
  - `GET /ready`;
  - `POST /pre-analyze`;
  - `POST /process`;
  - `GET /api/search`;
  - `POST /search`;
  - `DELETE /cache/{drawing_id}`.
- Добавлена валидация путей к файлам внутри разрешённого `dataset`.
- Подключены OCR, YOLO, RAG/FAISS и LangGraph.
- PostgreSQL используется как checkpoint-хранилище LangGraph.
- Подключён OpenAI-совместимый LLM API.
- Поддержаны локальные offline-модели:
  - `drawing_agent/models/best.pt`;
  - `drawing_agent/models/easyocr`;
  - `drawing_agent/models/transformers/all-MiniLM-L6-v2`.
- Добавлен выбор устройства через `AGENT_DEVICE`: `cpu`, `cuda`, `auto`.
- Добавлен PyTorch index через `TORCH_INDEX_URL`.

### Docker и запуск

- Подготовлены Dockerfile для сервисов.
- `docker-compose.yml` поднимает Redis, MongoDB, PostgreSQL, backend, frontend, worker и agent.
- CPU-запуск выполняется командой:

```powershell
docker compose up --build
```

- GPU-запуск выполняется командой:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

- Для GPU-режима добавлены:
  - `gpus: all`;
  - `NVIDIA_VISIBLE_DEVICES=all`;
  - `NVIDIA_DRIVER_CAPABILITIES=compute,utility`;
  - CUDA PyTorch index `https://download.pytorch.org/whl/cu121`.

### Конфигурация и безопасность

- Добавлен `.env.example` с базовыми переменными окружения.
- Ключ LLM задаётся через `OPENAI_API_KEY`, а в Docker Compose передаётся в `drawing_agent` как Docker secret.
- Секрет удалён из `drawing_agent/config/model/ollama.yaml`.
- Конфигурация CPU/GPU вынесена в `AGENT_DEVICE` и `TORCH_INDEX_URL`.

### Документация

- Обновлён README под фактическую структуру проекта.
- Добавлено оглавление README.
- Добавлено оглавление ROADMAP.
- Добавлены инструкции запуска на CPU и GPU.
- Описаны переменные окружения.
- Описаны основные endpoint'ы backend и `drawing_agent`.
- ROADMAP приведён к формату ретроспективы выполненных работ.

## Примерная недельная хронология работ

### 23-29 марта

- Сформирована начальная структура проекта.
- Добавлены первые файлы и базовые зависимости.
- Начата подготовка набора тестовых данных для строительных чертежей.
- Зафиксирована идея MVP: загрузка чертежа, анализ, описание, вопросы и поиск.
- Намечено разделение будущей системы на backend, frontend и AI-модуль.

### 30 марта - 5 апреля

- Начата проработка AI-части проекта.
- Добавлены первые файлы агента и заготовки пайплайна анализа.
- Подготовлены базовые конфиги моделей.
- Начата интеграция OCR и обработки изображений.
- Начата подготовка структуры для извлечения данных из чертежей.

### 6-12 апреля

- Продолжена работа над `drawing_agent`.
- Добавлены компоненты для structured extraction и `instructor`.
- Подготовлены зависимости для Python-сервисов.
- Начата упаковка сервисов в Docker.
- Добавлены первые Dockerfile и requirements.
- Сформирована база для дальнейшей интеграции LLM, OCR и анализа изображений.

### 13-20 апреля

- Расширена инфраструктура Docker.
- Добавлены и уточнены Dockerfile сервисов.
- Подготовлена основа backend-сервиса.
- Начата сборка frontend-части.
- Добавлены первые workflow и CI-заготовки.
- Подготовлена модельная часть агента, включая YOLO-модель.
- Начата интеграция сервисов в общий стек.

### Работы, завершённые после базового недельного этапа

- Собран полный Docker Compose стек с Redis, MongoDB и PostgreSQL.
- Добавлен Celery worker и фоновая обработка задач.
- Реализован FastAPI backend с загрузкой, поиском, вопросами, удалением и WebSocket.
- Реализован frontend с основными пользовательскими сценариями.
- Добавлен RAG/FAISS поиск и кеширование.
- Добавлена работа с локальными offline-моделями.
- Добавлен PostgreSQL checkpoint для LangGraph.
- Добавлены CPU/GPU режимы запуска.
- Обновлены README и ROADMAP.
