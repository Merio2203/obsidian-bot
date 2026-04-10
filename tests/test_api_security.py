from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import quote

import pytest

from bot.api.security import TelegramAuthError, validate_telegram_init_data


def _build_init_data(bot_token: str, user_id: int = 42) -> str:
    user_json = json.dumps(
        {"id": user_id, "first_name": "Test", "username": "tester"},
        separators=(",", ":"),
        ensure_ascii=False,
    )
    fields = {
        "auth_date": "1710000000",
        "query_id": "AAEAAAE",
        "user": user_json,
    }
    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields.keys()))
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    digest = hmac.new(secret, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return (
        f"query_id={quote(fields['query_id'])}"
        f"&user={quote(user_json)}"
        f"&auth_date={fields['auth_date']}"
        f"&hash={digest}"
    )


def test_validate_telegram_init_data_success() -> None:
    init_data = _build_init_data("token-123", user_id=777)
    user = validate_telegram_init_data(init_data, "token-123")
    assert user.id == 777
    assert user.username == "tester"


def test_validate_telegram_init_data_invalid_hash() -> None:
    init_data = _build_init_data("token-123", user_id=777) + "broken"
    with pytest.raises(TelegramAuthError):
        validate_telegram_init_data(init_data, "token-123")
