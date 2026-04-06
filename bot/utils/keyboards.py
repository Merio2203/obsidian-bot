"""Клавиатуры Telegram для интерфейса бота."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Возвращает клавиатуру главного меню."""
    keyboard = [
        ["📁 Проекты", "✅ Задачи"],
        ["📓 Дневник", "💡 Идея"],
        ["📚 Ресурс", "📥 Входящие"],
        ["📊 Сегодня", "⚙️ Настройки"],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_projects_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура меню раздела проектов."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Создать проект", callback_data="projects:create")],
            [InlineKeyboardButton("📚 Список проектов", callback_data="projects:list")],
            [InlineKeyboardButton("◀️ Назад в главное меню", callback_data="projects:back")],
        ]
    )


def get_project_status_keyboard(project_id: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора нового статуса проекта."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🟡 Активный", callback_data=f"projects:set_status:{project_id}:active")],
            [InlineKeyboardButton("⏸ На паузе", callback_data=f"projects:set_status:{project_id}:paused")],
            [InlineKeyboardButton("🟢 Завершён", callback_data=f"projects:set_status:{project_id}:done")],
        ]
    )


def get_project_actions_keyboard(project_id: int) -> InlineKeyboardMarkup:
    """Клавиатура действий внутри конкретного проекта."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Задачи проекта", callback_data=f"projects:tasks:{project_id}")],
            [InlineKeyboardButton("🔄 Изменить статус", callback_data=f"projects:status:{project_id}")],
            [InlineKeyboardButton("🗃 Архивировать", callback_data=f"projects:archive:{project_id}")],
            [InlineKeyboardButton("⬅️ К списку", callback_data="projects:list")],
        ]
    )
