"""Клавиатуры Telegram для интерфейса бота."""

from telegram import ReplyKeyboardMarkup


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Возвращает клавиатуру главного меню."""
    keyboard = [
        ["📁 Проекты", "✅ Задачи"],
        ["📓 Дневник", "💡 Идея"],
        ["📚 Ресурс", "📥 Входящие"],
        ["📊 Сегодня", "⚙️ Настройки"],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

