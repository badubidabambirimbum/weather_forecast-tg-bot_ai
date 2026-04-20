"""Проверка initData от Telegram Web App: https://core.telegram.org/bots/webapp#validating-data-received-via-the-mini-app"""

from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import parse_qsl


def verify_init_data(init_data: str, bot_token: str) -> dict[str, str]:
    """
    Возвращает распарсенные пары ключ-значение при успешной проверке подписи.
    """
    pairs = dict(parse_qsl(init_data, strict_parsing=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise ValueError("Нет hash в initData")

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs.keys()))
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode(),
        hashlib.sha256,
    ).digest()
    computed = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    if computed != received_hash:
        raise ValueError("Неверная подпись initData")

    if "user" in pairs:
        try:
            pairs["user"] = json.loads(pairs["user"])
        except json.JSONDecodeError:
            pass
    return pairs
