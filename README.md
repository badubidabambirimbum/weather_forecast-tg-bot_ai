# Telegram Weather Mini App

MVP Telegram Weather Mini App:
- backend на `FastAPI` отдает API и статический Mini App;
- Telegram-бот на `aiogram` отправляет кнопку открытия WebApp;
- фронтенд Mini App запрашивает прогноз через `GET /api/forecast`;
- backend предоставляет API прогноза погоды через Open-Meteo.

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
  - форма: город, выбор периода `1 / 3 / 10` дней, кнопка `Показать прогноз` -> `GET /api/forecast`;
  - список дней: дата, min/max °C, описание погоды (по коду Open‑Meteo).
- Backend (`backend/app.py`):
  - `GET /health` -> `{"ok": true}`;
  - `GET /api/forecast?city=<город>&days=<1|3|10>` -> дневной прогноз;
  - раздача статики Mini App по корневому пути `/`.
- Слой интеграции с погодным API:
  - `backend/services/open_meteo.py` реализует геокодинг и получение прогноза из Open-Meteo;
  - данные нормализуются в единый формат ответа (`date`, `min_temp_c`, `max_temp_c`, `weather`).

## Pipeline запуска для пользователя

### 1) Prerequisites

- Python 3.10+.
- Telegram-бот с токеном от `@BotFather`.
- Публичный `https://` URL (например, через туннель), доступный из Telegram.
- Доступ в интернет для вызова Open-Meteo API.

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

Опционально для backend (уровень логов пакета `backend` при запуске через uvicorn):

- `LOG_LEVEL` - `DEBUG`, `INFO`, `WARNING` или `ERROR` (по умолчанию `INFO`).

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
curl "http://127.0.0.1:8000/api/forecast?city=Moscow&days=3"
```

Проверьте пользовательский сценарий:
1. Откройте чат с ботом и отправьте `/start`.
2. Нажмите `Открыть mini app`.
3. Введите город (например `Москва`), выберите `1`, `3` или `10` дней, нажмите `Показать прогноз`.
4. Должен появиться список строк вида `YYYY-MM-DD: min … max, описание`.

Проверьте API прогноза:
- запрос: `GET /api/forecast?city=Moscow&days=3`;
- ожидаемо: `200 OK` и массив `forecast` из 3 элементов;
- при `days` не из набора `1/3/10` ожидается `422`.

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
  schemas.py             # Pydantic-схемы для запроса/ответа API прогноза
  services/
    open_meteo.py        # Клиент Open-Meteo (геокодинг + дневной прогноз)
bot/
  main.py                # Telegram-бот (aiogram), команда /start и WebApp-кнопка
miniapp/
  index.html             # UI Mini App
  app.js                 # Вызов /api/forecast, разбор ошибок API
  styles.css             # Стили интерфейса Mini App
tests/
  test_api.py            # API smoke-тесты для /health и /api/forecast
requirements.txt         # Python-зависимости
.env.example             # Пример переменных окружения
```

## Тесты

Сейчас в проекте есть API-тесты:
- `test_health_endpoint` проверяет доступность и контракт `/health`;
- `test_forecast_endpoint_success` проверяет успешный ответ `/api/forecast` с мокнутым клиентом Open-Meteo;
- `test_forecast_endpoint_validation_error` проверяет валидацию `days` (допустимы только `1/3/10`).

Запуск всех тестов:

```bash
python -m pytest
```

Успешный результат:
- `3 passed` (или больше, если добавлены новые тесты);
- без ошибок импорта и падений endpoint'ов.

