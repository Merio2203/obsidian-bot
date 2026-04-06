"""Хендлеры главного меню."""

from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from bot.utils.decorators import owner_only
from bot.utils.keyboards import get_main_menu_keyboard

MENU_RESPONSES = {
    "💡 Идея": "💡 Режим быстрых идей скоро будет доступен.",
    "📚 Ресурс": "📚 Сохранение статей и видео будет добавлено следующим этапом.",
    "📥 Входящие": "📥 Раздел входящих заметок скоро появится.",
    "📊 Сегодня": "📊 Дашборд дня подключим после интеграции календаря и задач.",
    "⚙️ Настройки": "⚙️ Настройки будут доступны в следующих итерациях.",
}


@owner_only
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает главное меню бота."""
    if not update.effective_message:
        return

    await update.effective_message.reply_text(
        "Привет! Я ваш Obsidian AI-ассистент.\nВыберите нужный раздел в меню ниже.",
        reply_markup=get_main_menu_keyboard(),
    )


@owner_only
async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Маршрутизирует текстовые кнопки главного меню."""
    if not update.effective_message or not update.effective_message.text:
        return

    text = update.effective_message.text.strip()
    response = MENU_RESPONSES.get(
        text,
        "Не понял команду. Используйте кнопки меню или команду /start.",
    )
    await update.effective_message.reply_text(response, reply_markup=get_main_menu_keyboard())


def register_menu_handlers(application: Application) -> None:
    """Регистрирует хендлеры главного меню в приложении."""
    application.add_handler(CommandHandler("start", start_handler))
    # Важно держать fallback-меню в отдельной группе, чтобы профильные ConversationHandler
    # (проекты/задачи/дневник) перехватывали свои кнопки раньше.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_router), group=10)
