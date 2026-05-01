# Telegram Weather Mini App - Шаг 1

Минимальный production-like каркас Telegram Mini App:
- backend на `FastAPI` отдает API и статический Mini App;
- Telegram-бот на `aiogram` отправляет кнопку открытия WebApp;
- фронтенд Mini App делает запрос в API и показывает mock-ответ.

## Содержание

- [Функциональности](#функциональности)
- [Pipeline запуска для пользователя](#pipeline-запуска-для-пользователя)
  - [1) Prerequisites](#1-prerequisites)
  - [2) Установка зависимостей](#2-установка-зависимостей)
  - [3) Настройка окружения](#3-настройка-окружения)
  - [4) Запуск компонентов](#4-запуск-компонентов)
  - [5) Как поднять публичный URL для локального backend](#5-как-поднять-публичный-url-для-локального-backend)
  - [6) Базовая проверка, что все поднялось](#6-базовая-проверка-что-все-поднялось)
  - [Быстрый запуск (кратко)](#быстрый-запуск-кратко)
- [Структура проекта](#структура-проекта)
- [Тесты](#тесты)

## Функциональности

- Команда `/start` в боте:
  - проверяет корректность `MINIAPP_URL` (только публичный `https://`);
  - показывает кнопку `Открыть mini app` при валидном URL;
  - возвращает понятное сообщение, если URL не настроен.
- Mini App (`miniapp/index.html`, `miniapp/app.js`):
  - инициализируется через Telegram WebApp SDK;
  - по кнопке `Проверить mini app` вызывает `GET /api/mock`;
  - отображает ответ API или текст ошибки.
- Backend (`backend/app.py`):
  - `GET /health` -> `{"ok": true}`;
  - `GET /api/mock` -> тестовое сообщение;
  - раздача статики Mini App по корневому пути `/`.

## Pipeline запуска для пользователя

### 1) Prerequisites

- Python 3.10+.
- Telegram-бот с токеном от `@BotFather`.
- Публичный `https://` URL (например, через туннель), доступный из Telegram.

### 2) Установка зависимостей

```bash
pip install -r requirements.txt
```

### 3) Настройка окружения

Создайте `.env` из шаблона:

```bash
copy .env.example .env
```

Заполните переменные:
- `BOT_TOKEN` - токен Telegram-бота;
- `MINIAPP_URL` - публичный `https://` URL backend (без локальных `http://localhost`).

### 4) Запуск компонентов

Запустите backend:

```bash
uvicorn backend.app:app --reload --port 8000
```

В отдельном терминале запустите бота:

```bash
python bot/main.py
```

### 5) Как поднять публичный URL для локального backend

Telegram Mini App не откроет локальный `http://127.0.0.1:8000`, поэтому нужен публичный `https://` адрес.

#### Вариант: ngrok

1. Установите ngrok и авторизуйтесь:

```bash
ngrok config add-authtoken <YOUR_NGROK_TOKEN>
```

2. При запущенном backend (`127.0.0.1:8000`) откройте туннель:

```bash
ngrok http 8000
```

3. Скопируйте `https://...` URL из вывода ngrok и запишите его в `.env`:

```env
MINIAPP_URL=https://<your-ngrok-domain>
```

4. Перезапустите бота:

```bash
python bot/main.py
```

Примечания:
- URL туннеля может меняться при каждом новом запуске (если не настроен постоянный домен).
- После смены URL всегда обновляйте `MINIAPP_URL` и перезапускайте бота.

### 6) Базовая проверка, что все поднялось

Проверьте backend endpoint'ы:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/mock
```

Проверьте пользовательский сценарий:
1. Откройте чат с ботом и отправьте `/start`.
2. Нажмите `Открыть mini app`.
3. В Mini App нажмите `Проверить mini app`.
4. Ожидаемый результат: `Здесь скоро появится прогноз погоды, следите за новостями:)`.

### Быстрый запуск (кратко)

```bash
pip install -r requirements.txt
copy .env.example .env
uvicorn backend.app:app --reload --port 8000
ngrok http 8000
python bot/main.py
```

После запуска `ngrok` скопируйте `https://...` URL и укажите его в `.env`:

```env
MINIAPP_URL=https://<your-ngrok-domain>
```

## Структура проекта

```text
backend/
  app.py                 # FastAPI-приложение, API и раздача статики Mini App
  schemas.py             # Pydantic-схемы (заготовка под следующие шаги)
  services/              # Сервисный слой backend (заготовка)
bot/
  main.py                # Telegram-бот (aiogram), команда /start и WebApp-кнопка
miniapp/
  index.html             # UI Mini App
  app.js                 # Логика кнопки и вызова /api/mock
  styles.css             # Стили интерфейса Mini App
tests/
  test_api.py            # API smoke-тесты для /health и /api/mock
requirements.txt         # Python-зависимости
.env.example             # Пример переменных окружения
```

## Тесты

Сейчас в проекте есть API smoke-тесты:
- `test_health_endpoint` проверяет доступность и контракт `/health`;
- `test_mock_endpoint` проверяет ответ `/api/mock`.

Запуск всех тестов:

```bash
python -m pytest
```

Успешный результат:
- `2 passed` (или больше, если добавлены новые тесты);
- без ошибок импорта и падений endpoint'ов.
