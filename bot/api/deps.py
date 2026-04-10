"""Dependency функции для API."""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from bot.config import settings

from .security import TelegramAuthError, TelegramUser, validate_telegram_init_data


def get_current_user(x_telegram_init_data: str | None = Header(default=None)) -> TelegramUser:
    """Проверяет пользователя Telegram Mini App по заголовку."""
    if not x_telegram_init_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Telegram initData")
    try:
        user = validate_telegram_init_data(x_telegram_init_data, settings.telegram_bot_token)
    except TelegramAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    if user.id != settings.telegram_owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner-only access")

    return user
