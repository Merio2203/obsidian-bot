"""Клавиатуры Telegram для интерфейса бота."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

MAIN_MENU_BUTTONS = (
    "📁 Проекты",
    "✅ Задачи",
    "📓 Дневник",
    "📚 Библиотека",
    "📥 Входящие",
    "📊 Сегодня",
    "⚙️ Настройки",
)

MAIN_MENU_BUTTONS_REGEX = r"^(📁 Проекты|✅ Задачи|📓 Дневник|📚 Библиотека|📥 Входящие|📊 Сегодня|⚙️ Настройки)$"
REMOVE_KEYBOARD = ReplyKeyboardRemove()


def get_cancel_keyboard(cancel_callback: str = "cancel") -> InlineKeyboardMarkup:
    """Inline-клавиатура отмены для режимов ввода."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data=cancel_callback)]])


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Главная reply-клавиатура."""
    keyboard = [
        ["📁 Проекты", "✅ Задачи"],
        ["📓 Дневник", "📚 Библиотека"],
        ["📥 Входящие", "📊 Сегодня"],
        ["⚙️ Настройки"],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Совместимость со старым именем функции главного меню."""
    return get_main_reply_keyboard()


def get_tasks_reply_keyboard() -> ReplyKeyboardMarkup:
    """Контекстная reply-клавиатура раздела задач."""
    keyboard = [["➕ Создать задачу"], ["◀️ Назад"]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_task_project_select_keyboard(projects: list[str]) -> ReplyKeyboardMarkup:
    """Клавиатура выбора проекта при создании задачи."""
    buttons: list[list[KeyboardButton]] = [[KeyboardButton("Без проекта")]]
    for project_name in projects:
        buttons.append([KeyboardButton(project_name)])
    buttons.append([KeyboardButton("❌ Отмена")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def get_projects_reply_keyboard() -> ReplyKeyboardMarkup:
    """Контекстная reply-клавиатура раздела проектов."""
    keyboard = [["➕ Создать проект", "📋 Список проектов"], ["◀️ Назад"]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_project_detail_reply_keyboard() -> ReplyKeyboardMarkup:
    """Контекстная reply-клавиатура внутри карточки проекта."""
    keyboard = [["➕ Новая задача", "✅ Задачи проекта"], ["◀️ К списку проектов"]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_diary_reply_keyboard() -> ReplyKeyboardMarkup:
    """Контекстная reply-клавиатура дневника."""
    keyboard = [["📝 Новая запись", "📖 Читать"], ["✏️ Редактировать"], ["◀️ Назад"]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_resources_reply_keyboard() -> ReplyKeyboardMarkup:
    """Контекстная reply-клавиатура ресурсов."""
    keyboard = [["➕ Добавить в библиотеку", "📋 Список"], ["◀️ Назад"]]
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


def get_diary_mood_keyboard() -> ReplyKeyboardMarkup:
    """Reply-клавиатура выбора настроения для дневника."""
    keyboard = [["😊", "😐", "😔", "😤", "🤩"]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)


def get_diary_existing_entry_keyboard() -> InlineKeyboardMarkup:
    """Кнопки действий, если дневник за сегодня уже существует."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📖 Показать", callback_data="diary:show")],
            [InlineKeyboardButton("✍️ Редактировать", callback_data="diary:edit")],
            [InlineKeyboardButton("◀️ Назад", callback_data="diary:back")],
        ]
    )


def get_diary_edit_sections_keyboard() -> InlineKeyboardMarkup:
    """Кнопки выбора раздела дневника для редактирования."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🌅 Как прошёл день", callback_data="diary:edit_section:day")],
            [InlineKeyboardButton("✅ Что сделал", callback_data="diary:edit_section:done")],
            [InlineKeyboardButton("💭 Мысли и идеи", callback_data="diary:edit_section:ideas")],
            [InlineKeyboardButton("🎯 Планы на завтра", callback_data="diary:edit_section:tomorrow")],
        ]
    )
