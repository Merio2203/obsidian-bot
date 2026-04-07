"""Хендлеры раздела задач."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.database import SessionLocal
from bot.database.crud import (
    create_task,
    get_project_by_id,
    get_projects,
    get_task_by_id,
    get_tasks,
    update_task_status,
)
from bot.services.ai_service import AIService
from bot.services.google_calendar import GoogleCalendarService
from bot.services.obsidian_service import ObsidianService
from bot.services.settings_service import SettingsService
from bot.utils.decorators import owner_only
from bot.utils.formatters import render_task_markdown
from bot.utils.keyboards import (
    get_main_menu_keyboard,
    get_task_actions_keyboard,
    get_task_calendar_keyboard,
    get_task_priority_keyboard,
    get_task_status_keyboard,
    get_tasks_menu_keyboard,
)

logger = logging.getLogger(__name__)

TASK_MENU, TASK_PROJECT, TASK_TITLE, TASK_DESCRIPTION, TASK_PRIORITY, TASK_DEADLINE, TASK_ESTIMATE, TASK_CALENDAR = range(8)

TASK_STATUS_MAP = {
    "new": "🔴 Новая",
    "in_progress": "🟡 В работе",
    "done": "🟢 Готово",
    "paused": "⏸ На паузе",
}


def _parse_deadline(raw: str) -> Optional[date]:
    """Парсит дату дедлайна в формате ДД.ММ.ГГГГ."""
    value = raw.strip()
    if value == "-":
        return None
    return datetime.strptime(value, "%d.%m.%Y").date()


def _parse_estimate(raw: str) -> Optional[float]:
    """Парсит оценку времени в часах."""
    value = raw.strip()
    if value == "-":
        return None
    hours = float(value.replace(",", "."))
    if hours < 0:
        raise ValueError("Оценка времени не может быть отрицательной")
    return hours


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


def _task_text(task_id: int, title: str, status: str, priority: str, obsidian_path: str) -> str:
    return (
        f"✅ <b>{title}</b>\n"
        f"ID: {task_id}\n"
        f"Статус: {status}\n"
        f"Приоритет: {priority}\n"
        f"Файл: <code>{obsidian_path}</code>"
    )


@owner_only
async def tasks_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа раздела задач."""
    if not update.effective_message:
        return ConversationHandler.END
    await update.effective_message.reply_text(
        "Раздел задач.\nВыберите действие:",
        reply_markup=get_tasks_menu_keyboard(),
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
        await _ask_project_selection(query.message)
        return TASK_PROJECT

    if data == "tasks:list":
        await _send_tasks_list(query.message)
        return TASK_MENU

    if data == "tasks:back":
        await query.message.reply_text(
            "Возвращаю в главное меню.",
            reply_markup=get_main_menu_keyboard(),
        )
        return ConversationHandler.END

    if data.startswith("tasks:open:"):
        task_id = int(data.split(":")[-1])
        await _send_task_card(query.message, task_id)
        return TASK_MENU

    if data.startswith("tasks:status:"):
        task_id = int(data.split(":")[-1])
        await query.message.reply_text("Выберите новый статус:", reply_markup=get_task_status_keyboard(task_id))
        return TASK_MENU

    if data.startswith("tasks:set_status:"):
        parts = data.split(":")
        if len(parts) != 4:
            await query.message.reply_text("Не удалось разобрать команду смены статуса.")
            return TASK_MENU
        _, _, task_id_raw, status_key = parts
        task_id = int(task_id_raw)
        new_status = TASK_STATUS_MAP.get(status_key)
        if not new_status:
            await query.message.reply_text("Неизвестный статус.")
            return TASK_MENU
        await _set_task_status(query.message, task_id, new_status)
        return TASK_MENU

    if data.startswith("tasks:project:"):
        project_raw = data.split(":", 2)[-1]
        project_id = None if project_raw == "none" else int(project_raw)
        context.user_data["task_project_id"] = project_id
        await query.message.reply_text("Введите название задачи:")
        return TASK_TITLE

    return TASK_MENU


@owner_only
async def create_task_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет название задачи."""
    if not update.effective_message or not update.effective_message.text:
        return TASK_TITLE
    context.user_data["task_title"] = update.effective_message.text.strip()
    await update.effective_message.reply_text("Опишите задачу подробнее:")
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
    await update.effective_message.reply_text(
        "Введите дедлайн в формате ДД.ММ.ГГГГ или '-' если без дедлайна:",
        reply_markup=ReplyKeyboardRemove(),
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
    await update.effective_message.reply_text("Введите оценку времени в часах (например 2 или 1.5) либо '-'")
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
    """Финализирует создание задачи."""
    if not update.effective_message or not update.effective_message.text:
        return TASK_CALENDAR

    calendar_choice = update.effective_message.text.strip().lower()
    if calendar_choice not in ("да", "нет"):
        await update.effective_message.reply_text("Выберите 'Да' или 'Нет'.", reply_markup=get_task_calendar_keyboard())
        return TASK_CALENDAR

    project_id = context.user_data.get("task_project_id")
    title = context.user_data.get("task_title", "").strip()
    description = context.user_data.get("task_description", "").strip()
    priority = context.user_data.get("task_priority", "⚡ Средний")
    deadline = context.user_data.get("task_deadline")
    estimate = context.user_data.get("task_estimate")

    if not title or not description:
        await update.effective_message.reply_text(
            "Не удалось собрать данные задачи. Начните заново.",
            reply_markup=get_main_menu_keyboard(),
        )
        return ConversationHandler.END

    project_name = "Без проекта"
    project_folder = "📥 Входящие"
    if project_id is not None:
        async with SessionLocal() as session:
            project = await get_project_by_id(session, project_id)
        if project:
            project_name = project.name
            project_dir = project.name.replace("/", "-")
            project_folder = f"📁 Проекты/{project_dir}/✅ Задачи"
        else:
            project_id = None

    ai_service = AIService(SessionLocal)
    obsidian = ObsidianService()
    existing_links = await obsidian.get_existing_links("all")
    final_title = title
    tags: list[str] = ["задача"]
    links: list[str] = [f"[[{project_name}]]"] if project_name != "Без проекта" else []
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
            try:
                runtime = await SettingsService(SessionLocal).get_runtime_settings()
                calendar_service = GoogleCalendarService(runtime.timezone)
                google_event_id = await calendar_service.create_event_for_task(
                    title=final_title,
                    description=description,
                    due_date=deadline,
                )
                if google_event_id:
                    calendar_note = "📅 Добавлено в Google Calendar."
                else:
                    calendar_note = "📅 Calendar недоступен: проверь токен Google OAuth."
            except Exception:  # noqa: BLE001
                logger.error("Ошибка создания события Calendar", exc_info=True)
                calendar_note = "📅 Не удалось создать событие в Calendar."

    file_name = f"{obsidian.sanitize_filename(final_title)}.md"
    relative_path = f"{project_folder}/{file_name}"
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    markdown = render_task_markdown(
        title=final_title,
        project_name=project_name,
        priority=priority,
        description=description,
        deadline_iso=deadline.isoformat() if deadline else None,
        estimated_time=estimate,
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
        f"Задача создана:\n\n{_task_text(task.id, task.title, task.status, task.priority, task.obsidian_path)}\n\n{sync_note}\n{calendar_note}",
        parse_mode="HTML",
        reply_markup=get_tasks_menu_keyboard(),
    )

    for key in ("task_project_id", "task_title", "task_description", "task_priority", "task_deadline", "task_estimate"):
        context.user_data.pop(key, None)
    return TASK_MENU


@owner_only
async def cancel_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет текущую операцию в задачах."""
    if update.effective_message:
        await update.effective_message.reply_text(
            "Операция отменена. Возвращаю в главное меню.",
            reply_markup=get_main_menu_keyboard(),
        )
    return ConversationHandler.END


async def _ask_project_selection(message) -> None:  # type: ignore[no-untyped-def]
    async with SessionLocal() as session:
        projects = await get_projects(session)

    rows = []
    for project in projects:
        rows.append([InlineKeyboardButton(project.name, callback_data=f"tasks:project:{project.id}")])
    rows.append([InlineKeyboardButton("Без проекта", callback_data="tasks:project:none")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="tasks:back")])
    await message.reply_text("Выберите проект для задачи:", reply_markup=InlineKeyboardMarkup(rows))


async def _send_tasks_list(message) -> None:  # type: ignore[no-untyped-def]
    async with SessionLocal() as session:
        tasks = await get_tasks(session)

    if not tasks:
        await message.reply_text("Пока нет задач. Нажмите «➕ Создать задачу».")
        return

    rows = []
    for task in tasks[:20]:
        rows.append([InlineKeyboardButton(f"{task.status} {task.title}", callback_data=f"tasks:open:{task.id}")])
    rows.append([InlineKeyboardButton("◀️ Назад", callback_data="tasks:back")])
    await message.reply_text("Список задач:", reply_markup=InlineKeyboardMarkup(rows))


async def _send_task_card(message, task_id: int) -> None:  # type: ignore[no-untyped-def]
    async with SessionLocal() as session:
        task = await get_task_by_id(session, task_id)
    if not task:
        await message.reply_text("Задача не найдена.")
        return
    await message.reply_text(
        _task_text(task.id, task.title, task.status, task.priority, task.obsidian_path),
        parse_mode="HTML",
        reply_markup=get_task_actions_keyboard(task.id),
    )


async def _set_task_status(message, task_id: int, status: str) -> None:  # type: ignore[no-untyped-def]
    async with SessionLocal() as session:
        task = await get_task_by_id(session, task_id)
        if not task:
            await message.reply_text("Задача не найдена.")
            return
        await update_task_status(session, task, status)
    await message.reply_text(f"Статус задачи обновлён: {status}")
    await _send_task_card(message, task_id)


def register_tasks_handlers(application: Application) -> None:
    """Регистрирует ConversationHandler раздела задач."""
    conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r".*Задачи$"), tasks_entry),
            CommandHandler("tasks", tasks_entry),
        ],
        states={
            TASK_MENU: [CallbackQueryHandler(tasks_menu_callback, pattern=r"^tasks:")],
            TASK_PROJECT: [CallbackQueryHandler(tasks_menu_callback, pattern=r"^tasks:")],
            TASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_title)],
            TASK_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_description)],
            TASK_PRIORITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_priority)],
            TASK_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_deadline)],
            TASK_ESTIMATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_estimate)],
            TASK_CALENDAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_calendar)],
        },
        fallbacks=[CommandHandler("cancel", cancel_tasks)],
        per_chat=True,
        per_user=True,
    )
    application.add_handler(conversation)
