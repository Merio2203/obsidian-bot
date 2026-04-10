"""Хендлеры главного меню."""

from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from bot.config import settings
from bot.utils.decorators import owner_only
from bot.utils.keyboards import get_mini_app_keyboard


@owner_only
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает launcher-клавиатуру Mini App."""
    if not update.effective_message:
        return

    app_hint = (
        "Нажми кнопку ниже, чтобы открыть Telegram Mini App."
        if settings.mini_app_url
        else "MINI_APP_URL не настроен. Укажи URL в .env и перезапусти бота."
    )
    msg = await update.effective_message.reply_text(
        "Привет! Я ваш Obsidian AI-ассистент.\n"
        "Основной интерфейс теперь работает как Telegram App.\n\n"
        f"{app_hint}",
        reply_markup=get_mini_app_keyboard(),
    )
    if context and msg and getattr(msg, "message_id", None) is not None:
        context.user_data["menu_message_id"] = msg.message_id


@owner_only
async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Launcher fallback: переоткрывает приветствие по текстовым сообщениям."""
    if not update.effective_message or not update.effective_message.text:
        return

    await start_handler(update, context)


def register_menu_handlers(application: Application) -> None:
    """Регистрирует хендлеры главного меню в приложении."""
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("app", start_handler))
