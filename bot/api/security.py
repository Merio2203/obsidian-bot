"""Проверка initData Telegram WebApp."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from urllib.parse import parse_qsl


class TelegramAuthError(ValueError):
    """Ошибка аутентификации Telegram WebApp."""


@dataclass(frozen=True)
class TelegramUser:
    id: int
    username: str | None
    first_name: str | None


def validate_telegram_init_data(init_data: str, bot_token: str) -> TelegramUser:
    """Проверяет подпись initData и возвращает пользователя."""
    if not init_data:
        raise TelegramAuthError("Пустой initData")

    values: dict[str, str] = dict(parse_qsl(init_data, keep_blank_values=True))
    incoming_hash = values.pop("hash", "")
    if not incoming_hash:
        raise TelegramAuthError("В initData отсутствует hash")

    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values.keys()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, incoming_hash):
        raise TelegramAuthError("Подпись initData не прошла проверку")

    user_raw = values.get("user", "")
    if not user_raw:
        raise TelegramAuthError("В initData отсутствуют данные пользователя")

    try:
        user_obj = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise TelegramAuthError("Некорректный JSON в поле user") from exc

    user_id = int(user_obj.get("id")) if user_obj.get("id") is not None else 0
    if user_id <= 0:
        raise TelegramAuthError("Некорректный user.id")

    return TelegramUser(
        id=user_id,
        username=user_obj.get("username"),
        first_name=user_obj.get("first_name"),
    )
