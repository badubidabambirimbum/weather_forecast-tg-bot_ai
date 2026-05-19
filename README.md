# Telegram Weather Mini App

MVP Telegram Weather Mini App:
- backend на `FastAPI` отдает API и статический Mini App;
- Telegram-бот на `aiogram`: WebApp, команды `/help`, `/about`, `/ping`, `/forecast`, меню команд;
- фронтенд Mini App сначала создает серверную сессию через `POST /api/session`, затем запрашивает прогноз;
- backend предоставляет API прогноза погоды через Open-Meteo;
- PostgreSQL (Docker): профиль пользователя и история попыток прогноза (успех и ошибки) из Mini App и `/forecast`.

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
- [База данных](#база-данных)
- [Тесты](#тесты)

## Функциональности

- Бот (`bot/main.py`, `bot/forecast_args.py`):
  - `/start` — проверка `MINIAPP_URL` (`https://`) и подсказка открыть Mini App через кнопку меню слева от поля ввода (Menu Button), либо `/forecast`;
  - `/help` — список команд; `/about` — назначение и Open‑Meteo; `/ping` — ответ `pong`;
  - `/forecast <город> [1|3|10]` — текстовый прогноз в чате (тот же `OpenMeteoClient`, что у backend);
  - неизвестная команда с `/` и обычный текст — подсказка про `/help` или `/start`;
  - при старте вызывается `set_my_commands` (меню команд в Telegram);
  - команды логируются на `INFO` с `user_id` и `chat_id`, ошибки Open‑Meteo — `WARNING`, прочие при `/forecast` — `exception`;
  - при заданном `DATABASE_URL` upsert профиля в PostgreSQL на командах и запись попыток `/forecast` (`source=bot`).
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
  - `GET /health` -> `{"ok": true}`; при подключённой БД также `"db": true`;
  - `POST /api/session` -> проверка подписи Telegram `initData`, upsert профиля в БД, установка `HttpOnly` cookie `wf_session`;
  - `GET /api/public/config` -> публичные настройки (`bot_url`) для экрана ограничения доступа;
  - `GET /api/geocode?query=<строка>` -> подсказки городов (Open-Meteo Geocoding), только при валидной session cookie;
  - `GET /api/forecast?city=<город>&days=<1|3|10>` -> дневной прогноз и запись попытки в БД (`success` / ошибки), только при валидной session cookie;
  - `POST /api/events` -> `204`, логгер `backend.events` (строка с `event=`, `tg_user_id=`, `payload=`), in-memory rate limit (60/мин на IP), только при валидной session cookie;
  - раздача статики Mini App по корневому пути `/`.
- Слой интеграции с погодным API:
  - `backend/services/open_meteo.py` реализует геокодинг и получение прогноза из Open-Meteo;
  - данные нормализуются в единый формат ответа (`date`, `min_temp_c`, `max_temp_c`, `weather_code`, `weather`).

## Pipeline запуска для пользователя

### 1) Prerequisites

- Python 3.10+ (рекомендуется conda-окружение `project-env`).
- Docker — для PostgreSQL локально.
- Telegram-бот с токеном от `@BotFather`.
- Публичный `https://` URL (например, через туннель), доступный из Telegram.
- Доступ в интернет для вызова Open-Meteo API.

### 2) Установка зависимостей

```bash
conda activate project-env
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
- `DATABASE_URL` - PostgreSQL для профиля и истории прогнозов (`postgresql+asyncpg://...`, см. `.env.example`);
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` - для `docker compose` (должны совпадать с паролем в `DATABASE_URL`).

Опционально для backend (уровень логов пакета `backend` при запуске через uvicorn):

- `LOG_LEVEL` - `DEBUG`, `INFO`, `WARNING` или `ERROR` (по умолчанию `INFO`).
- `COOKIE_SAMESITE` - политика cookie (`lax`, `strict`, `none`), для Telegram Web/iframe обычно `none`;
- `COOKIE_SECURE` - `1` для HTTPS-среды (ngrok/prod), `0` для локального HTTP;
- `INIT_DATA_MAX_AGE_SEC` - максимальный возраст Telegram `initData` в секундах.

### 4) Запуск компонентов

PostgreSQL и миграции (один раз или после смены схемы):

```bash
docker compose up -d postgres
python -m alembic upgrade head
```

Запустите backend:

```bash
uvicorn backend.app:app --reload --port 8000
```

В отдельном терминале запустите бота:

```bash
python bot/main.py
```

В логах backend и бота при успешном подключении: `PostgreSQL: подключение установлено`.

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

При настроенной БД в `/health` ожидается `"db": true`.

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
conda activate project-env
pip install -r requirements.txt
copy .env.example .env
docker compose up -d postgres
python -m alembic upgrade head
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
  db/
    engine.py            # Async SQLAlchemy engine
    models.py            # ORM: users, forecast_requests
    repository.py        # upsert_user, record_forecast_request
  services/
    open_meteo.py        # Клиент Open-Meteo (геокодинг + дневной прогноз)
alembic/                 # Миграции схемы PostgreSQL
docker-compose.yml       # Сервис postgres:16-alpine
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
  test_repository.py     # Репозиторий БД на SQLite in-memory
  test_db_integration.py # Опционально: PostgreSQL (TEST_DATABASE_URL)
  test_forecast_args.py  # Парсинг аргументов /forecast для бота
  test_telegram_webapp.py# Тесты валидации initData (hash/auth_date/user)
  conftest.py            # Изоляция тестов от локального DATABASE_URL
requirements.txt         # Python-зависимости
.env.example             # Пример переменных окружения
```

## База данных

**СУБД:** PostgreSQL 16 в Docker (`docker-compose.yml`).

**Таблицы:**
- `users` — профиль Telegram (`telegram_user_id`, имя, username, `last_seen_at`, `last_seen_source`: `miniapp` | `bot`);
- `forecast_requests` — попытки прогноза: город, дни, `status` (`success`, `validation_error`, `open_meteo_error`, `server_error`), опционально `http_status` и `error_detail`.

**Когда пишется:**
- Mini App: `POST /api/session` → `users`; `GET /api/forecast` → `forecast_requests` (все исходы);
- Бот: команды с пользователем → `users`; `/forecast` с городом → `forecast_requests` (подсказка без города не пишется).

**Не хранится:** `init_data`, токены, cookie, полный JSON прогноза, события `POST /api/events` (только логи), настройки формы из `localStorage`.

**Миграции:** только через Alembic (`python -m alembic upgrade head`).

**Проверка данных:**

```bash
docker exec -it weather_forecast_postgres psql -U weather -d weather -c "SELECT telegram_user_id, username, last_seen_source FROM users;"
docker exec -it weather_forecast_postgres psql -U weather -d weather -c "SELECT id, source, query_city, status, created_at FROM forecast_requests ORDER BY id DESC LIMIT 10;"
```

**Персональные данные:** хранятся Telegram ID, имя/username и история запросов городов для аналитики и улучшения сервиса; Open-Meteo получает только название города при запросе прогноза.

## Тесты

**Unit/API (без Docker):**

```bash
conda activate project-env
python -m pytest
```

Основные сценарии:
- `test_api.py` — health, session, geocode, forecast, events; моки Open-Meteo и вызовов БД;
- `test_repository.py` — upsert пользователя и записи `forecast_requests` на SQLite in-memory;
- `test_forecast_args.py` — парсинг `/forecast`;
- `test_telegram_webapp.py` — валидация `initData`.

**Интеграция с PostgreSQL (опционально):**

```bash
set TEST_DATABASE_URL=postgresql+asyncpg://weather:PASSWORD@localhost:5432/weather
python -m pytest -m integration
```

Успешный результат unit-набора: **25 passed** (без `-m integration`); без ошибок импорта.

