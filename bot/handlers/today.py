"""Хендлер дашборда 'Сегодня'."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from bot.database import SessionLocal
from bot.database.crud import (
    get_diary_entry_by_date,
    get_overdue_tasks,
    get_tasks_in_status,
    get_tasks_with_deadline,
)
from bot.services.google_calendar import GoogleCalendarService
from bot.services.settings_service import SettingsService
from bot.utils.decorators import owner_only
from bot.utils.keyboards import get_main_menu_keyboard

logger = logging.getLogger(__name__)


async def _today_local_date():
    service = SettingsService(SessionLocal)
    runtime = await service.get_runtime_settings()
    tz = ZoneInfo(runtime.timezone)
    return datetime.now(tz).date()


def _fmt_task_list(items, empty_text: str) -> str:  # type: ignore[no-untyped-def]
    if not items:
        return empty_text
    lines = []
    for task in items[:7]:
        deadline = task.deadline.isoformat() if task.deadline else "без дедлайна"
        lines.append(f"- {task.title} ({task.priority}, {deadline})")
    return "\n".join(lines)


def _fmt_calendar_list(events) -> str:  # type: ignore[no-untyped-def]
    if not events:
        return "Событий в Google Calendar на сегодня нет."
    lines = []
    for event in events[:7]:
        lines.append(f"- {event.start_label}–{event.end_label} {event.title}")
    return "\n".join(lines)


async def build_today_dashboard_text() -> str:
    """Формирует текст дашборда на сегодня из локальных данных."""
    runtime = await SettingsService(SessionLocal).get_runtime_settings()
    today = await _today_local_date()
    async with SessionLocal() as session:
        today_deadline_tasks = await get_tasks_with_deadline(session, today)
        in_progress_tasks = await get_tasks_in_status(session, "🟡 В работе")
        overdue_tasks = await get_overdue_tasks(session, today)
        diary_entry = await get_diary_entry_by_date(session, today)
    try:
        google_events = await GoogleCalendarService(runtime.timezone).list_events_for_date(today)
    except Exception:
        logger.error("Не удалось получить события Google Calendar для дашборда", exc_info=True)
        google_events = []

    diary_status = "✅ Запись дневника за сегодня есть" if diary_entry else "⚠️ Дневник за сегодня еще не заполнен"
    return (
        f"📊 Дашборд на {today.isoformat()}\n\n"
        "## 🗓️ Задачи на сегодня\n"
        f"{_fmt_task_list(today_deadline_tasks, 'На сегодня задач с дедлайном нет.')}\n\n"
        "## 🔧 В работе\n"
        f"{_fmt_task_list(in_progress_tasks, 'Нет задач в статусе В работе.')}\n\n"
        "## ⏰ Просроченные\n"
        f"{_fmt_task_list(overdue_tasks, 'Просроченных задач нет.')}\n\n"
        "## 📅 Google Calendar\n"
        f"{_fmt_calendar_list(google_events)}\n\n"
        "## 📓 Дневник\n"
        f"{diary_status}"
    )


@owner_only
async def today_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает дашборд на сегодня."""
    if not update.effective_message:
        return
    text = await build_today_dashboard_text()
    await update.effective_message.reply_text(text, reply_markup=get_main_menu_keyboard())


def register_today_handlers(application: Application) -> None:
    """Регистрирует хендлеры дашборда 'Сегодня'."""
    application.add_handler(MessageHandler(filters.Regex(r".*Сегодня$"), today_entry))
    application.add_handler(CommandHandler("today", today_entry))
