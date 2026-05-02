---
name: Telegram weather miniapp
overview: "Создать Telegram-бота с Mini App: пользователь вводит город, выбирает период 1/3/10 дней и получает min/max температуру и погодные условия за выбранный диапазон (данные Open‑Meteo, без API‑ключа)."
todos:
  - id: miniapp-mock-first
    content: Сделать mock Mini App и проверить открытие + нажатие кнопки с заглушкой-ответом
    status: completed
  - id: bootstrap-project
    content: Создать каркас Python проекта и базовые директории bot/backend/miniapp
    status: completed
  - id: implement-bot-entry
    content: Реализовать aiogram-бота с /start и кнопкой открытия Mini App
    status: completed
  - id: implement-forecast-api
    content: Сделать FastAPI endpoint прогноза с интеграцией Open‑Meteo
    status: completed
  - id: build-miniapp-ui
    content: Сделать Mini App форму города/периода и отображение результатов
    status: completed
  - id: config-and-tests
    content: Добавить .env.example, минимальные тесты и README с запуском
    status: completed
isProject: false
---

# План реализации Telegram Weather Mini App

## Цель

Собрать MVP Telegram-бота на Python, где основной ввод/вывод выполняется через Mini App, а данные прогноза берутся из Open‑Meteo (геокодинг и дневной прогноз без API‑ключа).

## Архитектура

```mermaid
flowchart LR
  user[UserInTelegram] --> bot[AiogramBot]
  bot --> miniapp[WebMiniAppUI]
  miniapp --> api[FastAPIBackend]
  api --> openmeteo[OpenMeteoAPI]
  api --> miniapp
  miniapp --> user
```



## Что будет сделано

- Этап 1 (проверка Mini App интеграции): сделать mock-версию Mini App с одной кнопкой, которая при нажатии показывает сообщение: `Здесь скоро появится прогноз погоды, следите за новостями:)`; проверить, что Mini App корректно открывается из Telegram.
- Инициализировать Python-проект со структурой для `aiogram`-бота, `FastAPI`-backend и frontend Mini App.
- Реализовать Telegram-бота с кнопкой открытия Mini App (`web_app`) и базовой обработкой `/start`.
- Сделать Mini App интерфейс:
  - поле ввода города,
  - выбор периода прогноза (`1`, `3`, `10` дней),
  - кнопка получения прогноза,
  - отображение списка дней с `min/max` температурой и описанием погоды.
- Реализовать backend endpoint для прогноза (например, `GET /api/forecast?city=...&days=...`):
  - валидация входных параметров,
  - геокодинг города через Open‑Meteo Geocoding API,
  - запрос дневного прогноза через Open‑Meteo Forecast API и нормализация ответа для UI (в т.ч. описание по `weather_code`),
  - обработка ошибок (город не найден, недоступность внешнего API, сетевые ошибки).
- Добавить конфигурацию через `.env` (токен бота, публичный URL Mini App; ключ погоды не требуется).
- Добавить минимальные тесты backend логики (валидация и формат ответа) и инструкции запуска.

## Предлагаемая структура файлов

- `[project-root]/bot/main.py` — запуск бота и команда `/start`.
- `[project-root]/backend/app.py` — FastAPI приложение.
- `[project-root]/backend/services/open_meteo.py` — клиент Open‑Meteo (геокодинг + дневной прогноз).
- `[project-root]/backend/schemas.py` — модели запросов/ответов.
- `[project-root]/miniapp/index.html` и `[project-root]/miniapp/app.js` — UI Mini App.
- `[project-root]/.env.example` — пример переменных окружения.
- `[project-root]/README.md` — запуск, настройки, сценарий использования.

## Критерии готовности MVP

- На первом шаге Mini App открывается из Telegram и кнопка в mock-интерфейсе успешно показывает заглушку: `Здесь скоро появится прогноз погоды, следите за новостями:)`.
- Mini App открывается из Telegram-кнопки.
- По валидному городу и периоду `1/3/10` отображаются дни с `min/max` и описанием погоды.
- При ошибках пользователь получает понятное сообщение в UI.
- Проект запускается локально по инструкции из README.

