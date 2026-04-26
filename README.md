# Telegram Weather Mini App - Шаг 1

В репозитории оставлен только каркас для первого этапа: рабочий Telegram Mini App с тестовой кнопкой и mock-ответом.

## Что реализовано

- Бот на `aiogram` с `/start` и кнопкой `Открыть mini app`.
- Mini App страница (`miniapp/index.html`) с кнопкой `Проверить mini app`.
- Backend на `FastAPI`:
  - `GET /health` для проверки живости сервиса,
  - `GET /api/mock` для тестового ответа.
- Базовые тесты API в `tests/test_api.py`.

## Подготовка

1. Установите зависимости:

```bash
pip install -r requirements.txt
```

2. Создайте `.env` из примера:

```bash
copy .env.example .env
```

3. Заполните переменные:
- `BOT_TOKEN` — токен от `@BotFather`.
- `MINIAPP_URL` — публичный `https://` URL backend, который открывается в Telegram.

## Запуск

1. Запустите backend:

```bash
uvicorn backend.app:app --reload --port 8000
```

2. В другом терминале запустите бота:

```bash
python bot/main.py
```

## Проверка шага 1

1. Откройте чат с ботом и отправьте `/start`.
2. Нажмите кнопку `Открыть mini app`.
3. Нажмите кнопку `Проверить mini app`.
4. Ожидаемый текст:

`Здесь скоро появится прогноз погоды, следите за новостями:)`

## Тесты

```bash
pytest
```
