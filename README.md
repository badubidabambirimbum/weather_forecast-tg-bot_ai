# Telegram Weather Mini App

MVP Telegram Weather Mini App:
- backend на `FastAPI` отдает API и статический Mini App;
- Telegram-бот на `aiogram`: WebApp, команды `/help`, `/about`, `/ping`, `/forecast`, меню команд;
- фронтенд Mini App сначала создает серверную сессию через `POST /api/session`, затем запрашивает прогноз;
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

- Бот (`bot/main.py`, `bot/forecast_args.py`):
  - `/start` — проверка `MINIAPP_URL` (`https://`) и подсказка открыть Mini App через кнопку меню слева от поля ввода (Menu Button), либо `/forecast`;
  - `/help` — список команд; `/about` — назначение и Open‑Meteo; `/ping` — ответ `pong`;
  - `/forecast <город> [1|3|10]` — текстовый прогноз в чате (тот же `OpenMeteoClient`, что у backend);
  - неизвестная команда с `/` и обычный текст — подсказка про `/help` или `/start`;
  - при старте вызывается `set_my_commands` (меню команд в Telegram);
  - команды логируются на `INFO` с `user_id` и `chat_id`, ошибки Open‑Meteo — `WARNING`, прочие при `/forecast` — `exception`.
- Mini App (`miniapp/index.html`, `miniapp/app.js`, `miniapp/logger.js`, `miniapp/styles.css`):
  - инициализируется через Telegram WebApp SDK, цвета из `themeParams` (в т.ч. после смены темы);
  - при старте ждёт `Telegram.WebApp.initData`, отправляет его на `POST /api/session` и работает только после успешной серверной валидации;
  - если `initData` отсутствует/невалиден, показывает экран «только из Telegram» со ссылкой на бота;
  - форма: автофокус на город, подсказки городов при вводе (`GET /api/geocode`), `Enter` отправляет запрос, trim и валидация длины; срок — ползунок на три положения (1 / 3 / 10 дней);
  - последние город и период сохраняются в `localStorage` и подставляются при открытии; до трёх последних успешных городов — чипы под полем ввода;
  - карточки по дням: дата, emoji по `weather_code`, min/max °C, текст погоды с API;
  - skeleton при загрузке, отдельный блок ошибки, кнопка `disabled` на время запроса;
  - favicon-заглушка (data-URL), чтобы не было лишних 404 в логах;
  - события UI (`miniapp_ready`, `submit_forecast`, `forecast_ok`, `forecast_error`, `command_hint_used`) — `POST /api/events` через `logger.js`; в payload автоматически подмешиваются поля пользователя из `initDataUnsafe.user`, а сервер в логах использует `tg_user_id` из проверенной session cookie.
- Backend (`backend/app.py`):
  - `GET /health` -> `{"ok": true}`;
  - `POST /api/session` -> проверка подписи Telegram `initData` + установка подписанной `HttpOnly` cookie `wf_session`;
  - `GET /api/public/config` -> публичные настройки (`bot_url`) для экрана ограничения доступа;
  - `GET /api/geocode?query=<строка>` -> подсказки городов (Open-Meteo Geocoding), только при валидной session cookie;
  - `GET /api/forecast?city=<город>&days=<1|3|10>` -> дневной прогноз, только при валидной session cookie;
  - `POST /api/events` -> `204`, логгер `backend.events` (строка с `event=`, `tg_user_id=`, `payload=`), in-memory rate limit (60/мин на IP), только при валидной session cookie;
  - раздача статики Mini App по корневому пути `/`.
- Слой интеграции с погодным API:
  - `backend/services/open_meteo.py` реализует геокодинг и получение прогноза из Open-Meteo;
  - данные нормализуются в единый формат ответа (`date`, `min_temp_c`, `max_temp_c`, `weather_code`, `weather`).

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
- `SESSION_SECRET` - секрет подписи session cookie (длинная случайная строка);
- `BOT_URL` - ссылка на бота (`https://t.me/<bot_username>`) для fallback-экрана в Mini App;
- `MINIAPP_URL` - публичный `https://` URL backend (без локальных `http://localhost`).

Опционально для backend (уровень логов пакета `backend` при запуске через uvicorn):

- `LOG_LEVEL` - `DEBUG`, `INFO`, `WARNING` или `ERROR` (по умолчанию `INFO`).
- `COOKIE_SAMESITE` - политика cookie (`lax`, `strict`, `none`), для Telegram Web/iframe обычно `none`;
- `COOKIE_SECURE` - `1` для HTTPS-среды (ngrok/prod), `0` для локального HTTP;
- `INIT_DATA_MAX_AGE_SEC` - максимальный возраст Telegram `initData` в секундах.

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
curl "http://127.0.0.1:8000/api/public/config"
```

Проверьте пользовательский сценарий:
1. Откройте чат с ботом и отправьте `/start`.
2. Нажмите кнопку меню слева от поля ввода (`Открыть Mini App`).
3. Введите город (например `Москва`), ползунком выберите срок (`1` / `3` / `10` дней), нажмите `Показать прогноз`.
4. Должны появиться карточки по дням с температурой и описанием.

Проверьте API прогноза:
- прямой запрос `GET /api/forecast?city=Moscow&days=3` без session cookie вернёт `401`;
- в Mini App (открытом из Telegram через Menu Button) после `POST /api/session` запросы к `geocode/forecast/events` выполняются успешно;
- при `days` не из набора `1/3/10` ожидается `422` (после успешной авторизации).

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
  telegram_webapp.py     # Валидация Telegram initData (hash/auth_date/user)
  services/
    open_meteo.py        # Клиент Open-Meteo (геокодинг + дневной прогноз)
bot/
  main.py                # Telegram-бот (aiogram): команды, WebApp, set_my_commands
  forecast_args.py       # Парсинг /forecast и формат ответа (без токена при импорте)
miniapp/
  index.html             # UI Mini App
  app.js                 # Форма, /api/forecast, события через logger.js
  logger.js              # Клиентские события -> POST /api/events
  styles.css             # Стили интерфейса Mini App
tests/
  test_api.py            # API-тесты с проверкой session cookie и auth-потока
  test_forecast_args.py  # Парсинг аргументов /forecast для бота
  test_telegram_webapp.py# Тесты валидации initData (hash/auth_date/user)
requirements.txt         # Python-зависимости
.env.example             # Пример переменных окружения
```

## Тесты

Сейчас в проекте есть тесты:
- `test_health_endpoint` проверяет доступность и контракт `/health`;
- `test_geocode_endpoint_success` / `test_geocode_endpoint_empty` / `test_geocode_query_too_short` — `/api/geocode`;
- `test_events_endpoint_accepts_known_event` / `test_events_endpoint_rejects_unknown_event` / `test_events_endpoint_rate_limit_429` — `POST /api/events`;
- `test_forecast_endpoint_success` проверяет успешный ответ `/api/forecast` с мокнутым клиентом Open-Meteo;
- `test_forecast_endpoint_validation_error` проверяет отказ без авторизации (`401`);
- `test_forecast_args` — парсинг `/forecast` в `bot/forecast_args.py` (без `BOT_TOKEN`).
- `test_telegram_webapp` — валидация `initData`: успешный hash, mismatch, просрочка, тип `user.id`.

Запуск всех тестов:

```bash
python -m pytest
```

Успешный результат:
- `22 passed` (или больше, если добавлены новые тесты);
- без ошибок импорта и падений endpoint'ов.

