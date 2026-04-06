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


def get_tasks_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура меню задач."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Создать задачу", callback_data="tasks:create")],
            [InlineKeyboardButton("📋 Список задач", callback_data="tasks:list")],
            [InlineKeyboardButton("◀️ Назад в главное меню", callback_data="tasks:back")],
        ]
    )


def get_task_priority_keyboard() -> ReplyKeyboardMarkup:
    """Reply-клавиатура выбора приоритета."""
    keyboard = [["🔥 Высокий", "⚡ Средний", "🌿 Низкий"]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)


def get_task_calendar_keyboard() -> ReplyKeyboardMarkup:
    """Reply-клавиатура подтверждения добавления в календарь."""
    keyboard = [["Да", "Нет"]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)


def get_task_status_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Inline-клавиатура выбора статуса задачи."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔴 Новая", callback_data=f"tasks:set_status:{task_id}:new")],
            [InlineKeyboardButton("🟡 В работе", callback_data=f"tasks:set_status:{task_id}:in_progress")],
            [InlineKeyboardButton("🟢 Готово", callback_data=f"tasks:set_status:{task_id}:done")],
            [InlineKeyboardButton("⏸ На паузе", callback_data=f"tasks:set_status:{task_id}:paused")],
        ]
    )


def get_task_actions_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Inline-клавиатура действий задачи."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 Изменить статус", callback_data=f"tasks:status:{task_id}")],
            [InlineKeyboardButton("⬅️ К списку", callback_data="tasks:list")],
        ]
    )
