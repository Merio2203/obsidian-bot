"""Хендлеры главного меню."""

from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from bot.utils.decorators import owner_only
from bot.utils.keyboards import get_main_menu_keyboard


@owner_only
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает главное меню бота."""
    if not update.effective_message:
        return

    msg = await update.effective_message.reply_text(
        "Привет! Я ваш Obsidian AI-ассистент.\nВыберите нужный раздел в меню ниже.",
        reply_markup=get_main_menu_keyboard(),
    )
    if context and msg and getattr(msg, "message_id", None) is not None:
        context.user_data["menu_message_id"] = msg.message_id


@owner_only
async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Маршрутизирует текстовые кнопки главного меню."""
    if not update.effective_message or not update.effective_message.text:
        return

    return


def register_menu_handlers(application: Application) -> None:
    """Регистрирует хендлеры главного меню в приложении."""
    application.add_handler(CommandHandler("start", start_handler))
    # Fallback-меню сейчас не содержит активных кнопок, оставляем только /start.
