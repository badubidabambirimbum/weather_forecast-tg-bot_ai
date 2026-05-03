"""Проверка initData Telegram Mini App и извлечение профиля пользователя.

Модуль изолирует криптографическую валидацию от HTTP-слоя, чтобы логику было
удобно тестировать и переиспользовать в зависимостях FastAPI.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl


class TelegramInitDataError(ValueError):
    """Базовая ошибка валидации initData."""


class TelegramInitDataExpiredError(TelegramInitDataError):
    """initData валиден криптографически, но устарел по auth_date."""


@dataclass(frozen=True)
class TelegramUser:
    """Проверенный профиль пользователя из initData.user."""

    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None
    is_premium: bool | None = None


@dataclass(frozen=True)
class VerifiedInitData:
    """Результат проверки initData."""

    auth_date: int
    user: TelegramUser | None
    raw_fields: dict[str, str]


def _build_data_check_string(fields: dict[str, str]) -> str:
    """Собирает data_check_string по правилам Telegram."""
    lines = [f"{k}={v}" for k, v in sorted(fields.items()) if k != "hash"]
    return "\n".join(lines)


def _parse_user(raw_user: str | None) -> TelegramUser | None:
    """Безопасно парсит user JSON из initData."""
    if not raw_user:
        return None
    try:
        data = json.loads(raw_user)
    except json.JSONDecodeError as exc:
        raise TelegramInitDataError("initData.user: invalid JSON") from exc
    if not isinstance(data, dict):
        raise TelegramInitDataError("initData.user: expected object")
    if "id" not in data:
        raise TelegramInitDataError("initData.user: missing id")

    user_id_raw = data["id"]
    if not isinstance(user_id_raw, int):
        raise TelegramInitDataError("initData.user.id: expected int")
    if isinstance(user_id_raw, bool):
        raise TelegramInitDataError("initData.user.id: expected int")

    def _opt_str(key: str) -> str | None:
        val = data.get(key)
        if val is None:
            return None
        if not isinstance(val, str):
            raise TelegramInitDataError(f"initData.user.{key}: expected string")
        return val

    is_premium_raw = data.get("is_premium")
    if is_premium_raw is not None and not isinstance(is_premium_raw, bool):
        raise TelegramInitDataError("initData.user.is_premium: expected bool")

    return TelegramUser(
        id=user_id_raw,
        username=_opt_str("username"),
        first_name=_opt_str("first_name"),
        last_name=_opt_str("last_name"),
        language_code=_opt_str("language_code"),
        is_premium=is_premium_raw,
    )


def verify_init_data(
    init_data: str,
    *,
    bot_token: str,
    max_age_seconds: int = 86400,
    now_ts: int | None = None,
) -> VerifiedInitData:
    """Проверяет подпись initData и его свежесть, возвращает проверенные поля.

    Args:
        init_data: Сырая строка Telegram.WebApp.initData.
        bot_token: Токен бота (из backend env).
        max_age_seconds: Допустимый возраст auth_date в секундах.
        now_ts: Текущее время для тестируемости; None -> time.time().

    Returns:
        VerifiedInitData: Нормализованные поля после успешной проверки.

    Raises:
        TelegramInitDataError: Любая ошибка валидации/подписи.
        TelegramInitDataExpiredError: initData старее max_age_seconds.
    """
    if not init_data or not init_data.strip():
        raise TelegramInitDataError("initData is empty")
    if not bot_token or not bot_token.strip():
        raise TelegramInitDataError("bot token is empty")
    if max_age_seconds <= 0:
        raise TelegramInitDataError("max_age_seconds must be positive")

    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    fields = dict(pairs)
    recv_hash = fields.get("hash")
    if not recv_hash:
        raise TelegramInitDataError("initData.hash is missing")

    data_check_string = _build_data_check_string(fields)
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc_hash, recv_hash):
        raise TelegramInitDataError("initData hash mismatch")

    auth_date_raw = fields.get("auth_date")
    if auth_date_raw is None:
        raise TelegramInitDataError("initData.auth_date is missing")
    try:
        auth_date = int(auth_date_raw)
    except ValueError as exc:
        raise TelegramInitDataError("initData.auth_date is invalid") from exc

    now = int(time.time()) if now_ts is None else int(now_ts)
    if auth_date > now:
        raise TelegramInitDataError("initData.auth_date is in the future")
    age_seconds = now - auth_date
    if age_seconds > max_age_seconds:
        raise TelegramInitDataExpiredError("initData is too old")

    user = _parse_user(fields.get("user"))
    return VerifiedInitData(auth_date=auth_date, user=user, raw_fields=fields)
