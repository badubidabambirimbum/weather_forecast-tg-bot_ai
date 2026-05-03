import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest

from backend.telegram_webapp import (
    TelegramInitDataError,
    TelegramInitDataExpiredError,
    verify_init_data,
)


def _make_init_data(fields: dict[str, str], bot_token: str) -> str:
    """Собирает initData с корректным hash для тестов."""
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    payload = dict(fields)
    payload["hash"] = calc_hash
    return urlencode(payload)


def test_verify_init_data_success_and_parse_user() -> None:
    bot_token = "123456:TEST_BOT_TOKEN"
    fields = {
        "auth_date": "1700000000",
        "query_id": "AAEAAAE",
        "user": json.dumps(
            {
                "id": 123456789,
                "username": "alexey",
                "first_name": "Alexey",
                "last_name": "Ivanov",
                "language_code": "ru",
                "is_premium": True,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    init_data = _make_init_data(fields, bot_token)

    out = verify_init_data(init_data, bot_token=bot_token, max_age_seconds=86_400, now_ts=1700000001)
    assert out.auth_date == 1700000000
    assert out.user is not None
    assert out.user.id == 123456789
    assert out.user.username == "alexey"
    assert out.user.language_code == "ru"
    assert out.user.is_premium is True


def test_verify_init_data_hash_mismatch() -> None:
    bot_token = "123456:TEST_BOT_TOKEN"
    bad_init_data = "auth_date=1700000000&query_id=AAEAAAE&hash=deadbeef"

    with pytest.raises(TelegramInitDataError, match="hash mismatch"):
        verify_init_data(bad_init_data, bot_token=bot_token, now_ts=1700000001)


def test_verify_init_data_expired() -> None:
    bot_token = "123456:TEST_BOT_TOKEN"
    fields = {
        "auth_date": "1700000000",
        "query_id": "AAEAAAE",
        "user": json.dumps({"id": 1}, separators=(",", ":")),
    }
    init_data = _make_init_data(fields, bot_token)

    with pytest.raises(TelegramInitDataExpiredError, match="too old"):
        verify_init_data(init_data, bot_token=bot_token, max_age_seconds=10, now_ts=1700000100)


def test_verify_init_data_rejects_user_without_int_id() -> None:
    bot_token = "123456:TEST_BOT_TOKEN"
    fields = {
        "auth_date": "1700000000",
        "query_id": "AAEAAAE",
        "user": json.dumps({"id": "123"}, separators=(",", ":")),
    }
    init_data = _make_init_data(fields, bot_token)

    with pytest.raises(TelegramInitDataError, match="expected int"):
        verify_init_data(init_data, bot_token=bot_token, now_ts=1700000001)
