"""Декораторы безопасности и служебной логики."""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import settings

logger = logging.getLogger(__name__)

HandlerFunc = TypeVar(
    "HandlerFunc",
    bound=Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]],
)


def owner_only(handler: HandlerFunc) -> HandlerFunc:
    """Ограничивает доступ к хендлеру только владельцу бота."""

    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
        user = update.effective_user
        if not user or user.id != settings.telegram_owner_id:
            logger.warning("Отклонен доступ неавторизованного пользователя: %s", user.id if user else None)
            text = "⛔ Доступ запрещен. Этот бот доступен только владельцу."

            if update.callback_query:
                await update.callback_query.answer("Нет доступа", show_alert=True)
                if update.callback_query.message:
                    await update.callback_query.message.reply_text(text)
                return None

            if update.effective_message:
                await update.effective_message.reply_text(text)
            return None

        return await handler(update, context)

    return wrapper  # type: ignore[return-value]

