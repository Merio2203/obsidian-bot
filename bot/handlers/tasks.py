"""Хендлеры раздела задач."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.config import PROJECT_SUBFOLDERS, VAULT_FOLDERS
from bot.database import SessionLocal
from bot.database.crud import (
    create_task,
    get_project_by_id,
    get_projects,
    get_task_by_id,
    get_tasks,
    update_task_completed,
)
from bot.services.ai_service import AIService
from bot.services.google_calendar import GoogleCalendarService
from bot.services.obsidian_service import ObsidianService
from bot.services.settings_service import SettingsService
from bot.utils.decorators import owner_only
from bot.utils.formatters import render_task_markdown
from bot.utils.helpers import (
    ask_for_input,
    edit_or_send,
    handle_unexpected_menu_button,
    universal_cancel_handler,
)
from bot.utils.keyboards import (
    MAIN_MENU_BUTTONS_REGEX,
    get_main_menu_keyboard,
    get_task_actions_keyboard,
    get_task_project_select_keyboard,
    get_task_calendar_keyboard,
    get_task_deadline_keyboard,
    get_task_priority_keyboard,
    get_task_status_keyboard,
    get_tasks_reply_keyboard,
    get_default_skip_keyboard,
)

logger = logging.getLogger(__name__)

DEFAULT_INPUT_TOKEN = "-"
DEFAULT_SKIP_TEXT = "⏭ Пропустить"

(
    TASK_MENU,
    TASK_PROJECT,
    TASK_TITLE,
    TASK_DESCRIPTION,
    TASK_PRIORITY,
    TASK_DEADLINE,
    TASK_ESTIMATE,
    TASK_CALENDAR,
    TASK_CALENDAR_START,
    TASK_CALENDAR_END,
) = range(10)

TASK_COMPLETED_MAP = {
    "todo": False,
    "done": True,
}


def _parse_deadline(raw: str) -> Optional[date]:
    """Парсит дату дедлайна в формате ДД.ММ.ГГГГ."""
    value = raw.strip()
    normalized = value.lower()
    if value == DEFAULT_INPUT_TOKEN or value == DEFAULT_SKIP_TEXT:
        return None
    if normalized == "сегодня":
        return datetime.now().date()
    if normalized == "завтра":
        return (datetime.now() + timedelta(days=1)).date()
    return datetime.strptime(value, "%d.%m.%Y").date()


def _parse_estimate(raw: str) -> Optional[float]:
    """Парсит оценку времени в часах."""
    value = raw.strip()
    if value == DEFAULT_INPUT_TOKEN or value == DEFAULT_SKIP_TEXT:
        return None
    hours = float(value.replace(",", "."))
    if hours < 0:
        raise ValueError("Оценка времени не может быть отрицательной")
    return hours


def _parse_time_value(raw: str) -> time:
    """Парсит время в формате HH:MM."""
    value = raw.strip()
    return datetime.strptime(value, "%H:%M").time()


def _normalize_tags(raw: list[str] | str | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        source = [x.strip() for x in raw.split(",")]
    else:
        source = [str(x).strip() for x in raw]
    tags: list[str] = []
    for item in source:
        if not item:
            continue
        token = item.lower().replace(" ", "-")
        if token.startswith("#"):
            token = token[1:]
        if token and token not in tags:
            tags.append(token)
    return tags[:5]


def _normalize_links(raw: list[str] | str | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        source = [x.strip() for x in raw.split(",")]
    else:
        source = [str(x).strip() for x in raw]
    links: list[str] = []
    for item in source:
        if not item:
            continue
        token = item.strip()
        if token.startswith("[") and "](" in token and token.endswith(")"):
            label = token[1 : token.index("]")]
            target = token[token.index("](") + 2 : -1].strip()
            target = target.split("/")[-1]
            if target.endswith(".md"):
                target = target[:-3]
            token = f"[[{target}|{label}]]" if label and label != target else f"[[{target}]]"
        else:
            if token.startswith("[[") and token.endswith("]]"):
                inner = token[2:-2].strip()
            else:
                inner = token.strip("[]")
            target_part, sep, alias = inner.partition("|")
            target = target_part.split("/")[-1].strip()
            if target.endswith(".md"):
                target = target[:-3]
            token = f"[[{target}|{alias.strip()}]]" if sep and alias.strip() else f"[[{target}]]"
        if token not in links:
            links.append(token)
    return links[:8]


def _task_text(task_id: int, title: str, completed: bool, priority: str, obsidian_path: str) -> str:
    status_label = "✅ Выполнена" if completed else "🕒 В процессе"
    return (
        f"✅ <b>{title}</b>\n"
        f"ID: {task_id}\n"
        f"Статус: {status_label}\n"
        f"Приоритет: {priority}\n"
        f"Файл: <code>{obsidian_path}</code>"
    )


@owner_only
async def tasks_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа раздела задач."""
    if not update.effective_message:
        return ConversationHandler.END
    await update.effective_message.reply_text("✅ Раздел задач", reply_markup=get_tasks_reply_keyboard())
    await edit_or_send(
        update,
        context,
        "Раздел задач.\nВыберите действие:",
    )
    return TASK_MENU


@owner_only
async def tasks_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка inline-кнопок меню задач."""
    if not update.callback_query:
        return TASK_MENU
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data == "tasks:create":
        await _ask_project_selection(update, context)
        return TASK_PROJECT

    if data == "tasks:list":
        await _send_tasks_list(update, context)
        return TASK_MENU

    if data == "tasks:back":
        await edit_or_send(
            update,
            context,
            "Возвращаю в главное меню.",
        )
        await query.message.reply_text("Главное меню", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    if data.startswith("tasks:open:"):
        task_id = int(data.split(":")[-1])
        await _send_task_card(update, context, task_id)
        return TASK_MENU

    if data.startswith("tasks:status:"):
        task_id = int(data.split(":")[-1])
        await edit_or_send(
            update,
            context,
            "Выберите новый статус:",
            reply_markup=get_task_status_keyboard(task_id),
        )
        return TASK_MENU

    if data.startswith("tasks:set_status:"):
        parts = data.split(":")
        if len(parts) != 4:
            await edit_or_send(update, context, "Не удалось разобрать команду смены статуса.")
            return TASK_MENU
        _, _, task_id_raw, status_key = parts
        task_id = int(task_id_raw)
        completed = TASK_COMPLETED_MAP.get(status_key)
        if completed is None:
            await edit_or_send(update, context, "Неизвестный статус.")
            return TASK_MENU
        await _set_task_completed(update, context, task_id, completed)
        return TASK_MENU

    if data.startswith("tasks:project:"):
        project_raw = data.split(":", 2)[-1]
        project_id = None if project_raw == "none" else int(project_raw)
        context.user_data["task_project_id"] = project_id
        await ask_for_input(update, context, "Введите название задачи:", state=TASK_TITLE)
        return TASK_TITLE

    if data == "tasks:deadline:today":
        context.user_data["task_deadline"] = datetime.now().date()
        await ask_for_input(
            update,
            context,
            "Введите оценку времени в часах (например 2 или 1.5) либо '-'",
            state=TASK_ESTIMATE,
            inline_keyboard=get_default_skip_keyboard("tasks:estimate:skip"),
        )
        return TASK_ESTIMATE

    if data == "tasks:deadline:tomorrow":
        context.user_data["task_deadline"] = (datetime.now() + timedelta(days=1)).date()
        await ask_for_input(
            update,
            context,
            "Введите оценку времени в часах (например 2 или 1.5) либо '-'",
            state=TASK_ESTIMATE,
            inline_keyboard=get_default_skip_keyboard("tasks:estimate:skip"),
        )
        return TASK_ESTIMATE

    if data == "tasks:deadline:skip":
        context.user_data["task_deadline"] = None
        await ask_for_input(
            update,
            context,
            "Введите оценку времени в часах (например 2 или 1.5) либо '-'",
            state=TASK_ESTIMATE,
            inline_keyboard=get_default_skip_keyboard("tasks:estimate:skip"),
        )
        return TASK_ESTIMATE

    if data == "tasks:estimate:skip":
        context.user_data["task_estimate"] = None
        if update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_text(
                "Добавить задачу в Google Календарь?",
                reply_markup=get_task_calendar_keyboard(),
            )
        return TASK_CALENDAR

    if data == "tasks:calendar_start:skip":
        context.user_data["task_calendar_start"] = time(10, 0)
        if update.callback_query and update.callback_query.message:
            await ask_for_input(
                update,
                context,
                "Укажите время окончания события в формате ЧЧ:ММ (например 11:00):",
                state=TASK_CALENDAR_END,
                inline_keyboard=get_default_skip_keyboard("tasks:calendar_end:skip", button_text="⏭ По умолчанию +1 час"),
            )
        return TASK_CALENDAR_END

    if data == "tasks:calendar_end:skip":
        start_value = context.user_data.get("task_calendar_start") or time(10, 0)
        if isinstance(start_value, time):
            start_dt = datetime.combine(datetime.now().date(), start_value)
            context.user_data["task_calendar_end"] = (start_dt + timedelta(hours=1)).time()
        else:
            context.user_data["task_calendar_end"] = time(11, 0)
        return await _finalize_task_creation(update, context)

    return TASK_MENU


@owner_only
async def tasks_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка контекстных reply-кнопок раздела задач."""
    if not update.effective_message or not update.effective_message.text:
        return TASK_MENU
    text = update.effective_message.text.strip()
    if text == "➕ Создать задачу":
        await _ask_project_selection(update, context)
        return TASK_PROJECT
    if text == "⚙️ Настройки":
        from bot.handlers.settings import settings_entry

        await settings_entry(update, context)
        return ConversationHandler.END
    if text == "◀️ Назад":
        await update.effective_message.reply_text("Главное меню", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END
    return TASK_MENU


@owner_only
async def create_task_project_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет выбор проекта для задачи из reply-клавиатуры."""
    if not update.effective_message or not update.effective_message.text:
        return TASK_PROJECT
    text = update.effective_message.text.strip()
    if text == "❌ Отмена":
        return await universal_cancel_handler(update, context)
    if text == "Без проекта":
        context.user_data["task_project_id"] = None
        await ask_for_input(update, context, "Введите название задачи:", state=TASK_TITLE)
        return TASK_TITLE

    projects_map: dict[str, int] = context.user_data.get("task_projects_map", {})
    project_id = projects_map.get(text)
    if project_id is None:
        await update.effective_message.reply_text("Выберите проект кнопкой или нажмите «❌ Отмена».")
        return TASK_PROJECT

    context.user_data["task_project_id"] = project_id
    await ask_for_input(update, context, "Введите название задачи:", state=TASK_TITLE)
    return TASK_TITLE


@owner_only
async def create_task_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет название задачи."""
    if not update.effective_message or not update.effective_message.text:
        return TASK_TITLE
    context.user_data["task_title"] = update.effective_message.text.strip()
    await ask_for_input(update, context, "Опишите задачу подробнее:", state=TASK_DESCRIPTION)
    return TASK_DESCRIPTION


@owner_only
async def create_task_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет описание задачи."""
    if not update.effective_message or not update.effective_message.text:
        return TASK_DESCRIPTION
    context.user_data["task_description"] = update.effective_message.text.strip()
    await update.effective_message.reply_text(
        "Выберите приоритет:",
        reply_markup=get_task_priority_keyboard(),
    )
    return TASK_PRIORITY


@owner_only
async def create_task_priority(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет приоритет задачи."""
    if not update.effective_message or not update.effective_message.text:
        return TASK_PRIORITY

    priority = update.effective_message.text.strip()
    if priority not in ("🔥 Высокий", "⚡ Средний", "🌿 Низкий"):
        await update.effective_message.reply_text("Выберите приоритет кнопками.")
        return TASK_PRIORITY

    context.user_data["task_priority"] = priority
    await ask_for_input(
        update,
        context,
        "Введите дедлайн в формате ДД.ММ.ГГГГ.\nМожно нажать «Сегодня» или «Завтра». Для пропуска — «Без дедлайна».",
        state=TASK_DEADLINE,
        inline_keyboard=get_task_deadline_keyboard(),
    )
    return TASK_DEADLINE


@owner_only
async def create_task_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет дедлайн."""
    if not update.effective_message or not update.effective_message.text:
        return TASK_DEADLINE

    raw = update.effective_message.text.strip()
    try:
        deadline = _parse_deadline(raw)
    except ValueError:
        await update.effective_message.reply_text("Неверный формат. Используйте ДД.ММ.ГГГГ или '-'.")
        return TASK_DEADLINE

    context.user_data["task_deadline"] = deadline
    await ask_for_input(
        update,
        context,
        "Введите оценку времени в часах (например 2 или 1.5) либо '-'",
        state=TASK_ESTIMATE,
        inline_keyboard=get_default_skip_keyboard("tasks:estimate:skip"),
    )
    return TASK_ESTIMATE


@owner_only
async def create_task_estimate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет оценку времени."""
    if not update.effective_message or not update.effective_message.text:
        return TASK_ESTIMATE

    raw = update.effective_message.text.strip()
    try:
        estimate = _parse_estimate(raw)
    except ValueError:
        await update.effective_message.reply_text("Введите число часов (например 2 или 1.5) либо '-'.")
        return TASK_ESTIMATE

    context.user_data["task_estimate"] = estimate
    await update.effective_message.reply_text(
        "Добавить задачу в Google Календарь?",
        reply_markup=get_task_calendar_keyboard(),
    )
    return TASK_CALENDAR


@owner_only
async def create_task_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает решение по добавлению в Calendar и (при необходимости) запрашивает время."""
    if not update.effective_message or not update.effective_message.text:
        return TASK_CALENDAR

    calendar_choice = update.effective_message.text.strip().lower()
    if calendar_choice not in ("да", "нет"):
        await update.effective_message.reply_text("Выберите 'Да' или 'Нет'.", reply_markup=get_task_calendar_keyboard())
        return TASK_CALENDAR
    context.user_data["task_calendar_choice"] = calendar_choice

    deadline = context.user_data.get("task_deadline")
    if calendar_choice == "да" and deadline is not None:
        await ask_for_input(
            update,
            context,
            "Укажите время начала события в формате ЧЧ:ММ (например 10:00):",
            state=TASK_CALENDAR_START,
            inline_keyboard=get_default_skip_keyboard("tasks:calendar_start:skip", button_text="⏭ По умолчанию 10:00"),
        )
        return TASK_CALENDAR_START

    return await _finalize_task_creation(update, context)


@owner_only
async def create_task_calendar_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет время начала события календаря."""
    if not update.effective_message or not update.effective_message.text:
        return TASK_CALENDAR_START
    raw = update.effective_message.text.strip()
    try:
        start_value = _parse_time_value(raw)
    except ValueError:
        await update.effective_message.reply_text("Неверный формат времени. Используйте ЧЧ:ММ, например 10:00.")
        return TASK_CALENDAR_START
    context.user_data["task_calendar_start"] = start_value
    await ask_for_input(
        update,
        context,
        "Укажите время окончания события в формате ЧЧ:ММ (например 11:00):",
        state=TASK_CALENDAR_END,
        inline_keyboard=get_default_skip_keyboard("tasks:calendar_end:skip", button_text="⏭ По умолчанию +1 час"),
    )
    return TASK_CALENDAR_END


@owner_only
async def create_task_calendar_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет время окончания события календаря и завершает создание задачи."""
    if not update.effective_message or not update.effective_message.text:
        return TASK_CALENDAR_END
    raw = update.effective_message.text.strip()
    try:
        end_value = _parse_time_value(raw)
    except ValueError:
        await update.effective_message.reply_text("Неверный формат времени. Используйте ЧЧ:ММ, например 11:00.")
        return TASK_CALENDAR_END
    context.user_data["task_calendar_end"] = end_value
    return await _finalize_task_creation(update, context)


async def _finalize_task_creation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Финализирует создание задачи и запись в Obsidian/БД."""
    if not update.effective_message:
        return TASK_MENU

    project_id = context.user_data.get("task_project_id")
    title = context.user_data.get("task_title", "").strip()
    description = context.user_data.get("task_description", "").strip()
    priority = context.user_data.get("task_priority", "⚡ Средний")
    deadline = context.user_data.get("task_deadline")
    estimate = context.user_data.get("task_estimate")
    calendar_choice = str(context.user_data.get("task_calendar_choice", "нет")).lower()

    if not title or not description:
        await update.effective_message.reply_text(
            "Не удалось собрать данные задачи. Начните заново.",
            reply_markup=get_main_menu_keyboard(),
        )
        return ConversationHandler.END

    project_name = "Без проекта"
    project_folder = VAULT_FOLDERS["inbox"]
    if project_id is not None:
        async with SessionLocal() as session:
            project = await get_project_by_id(session, project_id)
        if project:
            project_name = project.name
            project_dir = ObsidianService.sanitize_filename(project.name)
            project_folder = f"{VAULT_FOLDERS['projects']}/{project_dir}/{PROJECT_SUBFOLDERS[0]}"
        else:
            project_id = None

    ai_service = AIService(SessionLocal)
    obsidian = ObsidianService()
    existing_links = await obsidian.get_existing_links("all")
    final_title = title
    tags: list[str] = ["задача"]
    links: list[str] = [f"[[Проект {project_name}]]"] if project_name != "Без проекта" else []
    try:
        short_title = await ai_service.generate_short_title(title, description)
        if short_title:
            final_title = short_title.strip()[:120]
    except Exception:
        logger.error("Не удалось сгенерировать короткий title задачи", exc_info=True)

    try:
        tags_links = await ai_service.generate_task_tags_and_links(
            title=final_title,
            description=description,
            project_name=project_name,
            existing_links=existing_links,
        )
        tags = _normalize_tags(tags_links.get("tags")) or tags
        ai_links = _normalize_links(tags_links.get("links"))
        for link in ai_links:
            if link not in links:
                links.append(link)
    except Exception:
        logger.error("Не удалось сгенерировать теги/связи для задачи", exc_info=True)

    google_event_id = None
    calendar_note = ""
    if calendar_choice == "да":
        if deadline is None:
            calendar_note = "📅 Не добавил в Calendar: для события нужен дедлайн."
        else:
            start_time = context.user_data.get("task_calendar_start") or time(10, 0)
            end_time = context.user_data.get("task_calendar_end") or time(11, 0)
            if not isinstance(start_time, time):
                start_time = time(10, 0)
            if not isinstance(end_time, time):
                end_time = time(11, 0)
            try:
                runtime = await SettingsService(SessionLocal).get_runtime_settings()
                calendar_service = GoogleCalendarService(runtime.timezone)
                google_event_id = await calendar_service.create_event_for_task(
                    title=final_title,
                    description=description,
                    due_date=deadline,
                    start_time=start_time,
                    end_time=end_time,
                )
                if google_event_id:
                    calendar_note = f"📅 Добавлено в Google Calendar ({start_time.strftime('%H:%M')}–{end_time.strftime('%H:%M')})."
                else:
                    calendar_note = "📅 Calendar недоступен: проверь токен Google OAuth."
            except Exception:  # noqa: BLE001
                logger.error("Ошибка создания события Calendar", exc_info=True)
                calendar_note = "📅 Не удалось создать событие в Calendar."

    file_stem = obsidian.slugify_filename(final_title)
    try:
        generated_slug = await ai_service.generate_task_slug(
            title=final_title,
            description=description,
            project_name=project_name if project_name != "Без проекта" else "",
        )
        if generated_slug:
            file_stem = obsidian.slugify_filename(generated_slug)
    except Exception:
        logger.error("Не удалось сгенерировать slug имени файла задачи", exc_info=True)

    file_name = f"{file_stem}.md"
    relative_path = f"{project_folder}/{file_name}"
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    markdown = render_task_markdown(
        title=final_title,
        project_name=project_name,
        priority=priority,
        description=description,
        deadline_iso=deadline.isoformat() if deadline else None,
        estimated_time=estimate,
        completed=False,
        created_at=created_at,
        tags=tags,
        links=links,
        google_calendar_id=google_event_id or "",
    )
    write_result = await obsidian.write_markdown(relative_path, markdown)

    async with SessionLocal() as session:
        task = await create_task(
            session=session,
            project_id=project_id,
            title=final_title,
            priority=priority,
            task_type="task",
            deadline=deadline,
            estimated_time=estimate,
            obsidian_path=relative_path,
            google_event_id=google_event_id,
        )

    sync_note = "✅ Sync в Dropbox выполнен." if write_result.synced else f"⚠️ Sync не выполнен: {write_result.sync_error}"
    await update.effective_message.reply_text(
        f"Задача создана:\n\n{_task_text(task.id, task.title, task.completed, task.priority, task.obsidian_path)}\n\n{sync_note}\n{calendar_note}",
        parse_mode="HTML",
    )
    await update.effective_message.reply_text("✅ Раздел задач", reply_markup=get_tasks_reply_keyboard())

    for key in (
        "task_project_id",
        "task_title",
        "task_description",
        "task_priority",
        "task_deadline",
        "task_estimate",
        "task_calendar_choice",
        "task_calendar_start",
        "task_calendar_end",
    ):
        context.user_data.pop(key, None)
    context.user_data.pop("expecting_text_input", None)
    context.user_data.pop("input_state", None)
    return TASK_MENU


@owner_only
async def cancel_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет текущую операцию в задачах."""
    return await universal_cancel_handler(update, context)


async def _ask_project_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        projects = await get_projects(session)

    projects_map = {project.name: project.id for project in projects}
    context.user_data["task_projects_map"] = projects_map
    project_names = list(projects_map.keys())
    if update.effective_message:
        await update.effective_message.reply_text(
            "Выберите проект для задачи:",
            reply_markup=get_task_project_select_keyboard(project_names),
        )
    elif update.callback_query and update.callback_query.message:
        await update.callback_query.message.reply_text(
            "Выберите проект для задачи:",
            reply_markup=get_task_project_select_keyboard(project_names),
        )


async def _send_tasks_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        tasks = await get_tasks(session)

    if not tasks:
        await edit_or_send(update, context, "Пока нет задач. Нажмите «➕ Создать задачу».")
        return

    rows = []
    for task in tasks[:20]:
        status_icon = "✅" if task.completed else "🕒"
        rows.append([InlineKeyboardButton(f"{status_icon} {task.title}", callback_data=f"tasks:open:{task.id}")])
    rows.append([InlineKeyboardButton("◀️ Назад", callback_data="tasks:back")])
    await edit_or_send(update, context, "Список задач:", reply_markup=InlineKeyboardMarkup(rows))


async def _send_task_card(update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: int) -> None:
    async with SessionLocal() as session:
        task = await get_task_by_id(session, task_id)
    if not task:
        await edit_or_send(update, context, "Задача не найдена.")
        return
    await edit_or_send(
        update,
        context,
        _task_text(task.id, task.title, task.completed, task.priority, task.obsidian_path),
        reply_markup=get_task_actions_keyboard(task.id),
    )


async def _set_task_completed(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    task_id: int,
    completed: bool,
) -> None:
    async with SessionLocal() as session:
        task = await get_task_by_id(session, task_id)
        if not task:
            await edit_or_send(update, context, "Задача не найдена.")
            return
        await update_task_completed(session, task, completed)
    if update.callback_query:
        label = "✅ Выполнена" if completed else "🕒 В процессе"
        await update.callback_query.answer(f"Статус обновлён: {label}", show_alert=False)
    await _send_task_card(update, context, task_id)


def register_tasks_handlers(application: Application) -> None:
    """Регистрирует ConversationHandler раздела задач."""
    conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r".*Задачи$"), tasks_entry),
            MessageHandler(filters.Regex(r"^➕ Создать задачу$"), tasks_entry),
            CommandHandler("tasks", tasks_entry),
        ],
        states={
            TASK_MENU: [
                CallbackQueryHandler(tasks_menu_callback, pattern=r"^tasks:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, tasks_menu_text),
            ],
            TASK_PROJECT: [
                CallbackQueryHandler(tasks_menu_callback, pattern=r"^tasks:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_project_select),
            ],
            TASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_title)],
            TASK_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_description)],
            TASK_PRIORITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_priority)],
            TASK_DEADLINE: [
                CallbackQueryHandler(tasks_menu_callback, pattern=r"^tasks:deadline:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_deadline),
            ],
            TASK_ESTIMATE: [
                CallbackQueryHandler(tasks_menu_callback, pattern=r"^tasks:estimate:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_estimate),
            ],
            TASK_CALENDAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_calendar)],
            TASK_CALENDAR_START: [
                CallbackQueryHandler(tasks_menu_callback, pattern=r"^tasks:calendar_start:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_calendar_start),
            ],
            TASK_CALENDAR_END: [
                CallbackQueryHandler(tasks_menu_callback, pattern=r"^tasks:calendar_end:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_calendar_end),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_tasks),
            CallbackQueryHandler(universal_cancel_handler, pattern=r"^cancel$"),
            MessageHandler(filters.TEXT & filters.Regex(MAIN_MENU_BUTTONS_REGEX), handle_unexpected_menu_button),
        ],
        per_chat=True,
        per_user=True,
    )
    application.add_handler(conversation)
