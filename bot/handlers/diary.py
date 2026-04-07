"""Хендлеры раздела дневника."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.config import VAULT_FOLDERS
from bot.database import SessionLocal
from bot.database.crud import create_diary_entry, get_diary_entry_by_date
from bot.services.obsidian_service import ObsidianService
from bot.services.settings_service import SettingsService
from bot.utils.decorators import owner_only
from bot.utils.formatters import render_diary_markdown
from bot.utils.helpers import edit_or_send
from bot.utils.keyboards import (
    get_diary_edit_sections_keyboard,
    get_diary_existing_entry_keyboard,
    get_diary_mood_keyboard,
    get_main_menu_keyboard,
)

logger = logging.getLogger(__name__)

(
    DIARY_ACTION,
    DIARY_MOOD,
    DIARY_DAY,
    DIARY_DONE,
    DIARY_IDEAS,
    DIARY_TOMORROW,
    DIARY_EDIT_CHOOSE_SECTION,
    DIARY_EDIT_INPUT_TEXT,
) = range(8)

DIARY_MOODS = {"😊", "😐", "😔", "😤", "🤩"}

DIARY_SECTIONS = {
    "day": "🌅 Как прошёл день",
    "done": "✅ Что сделал",
    "ideas": "💭 Мысли и идеи",
    "tomorrow": "🎯 Планы на завтра",
}


async def _today_local() -> datetime.date:
    runtime = await SettingsService(SessionLocal).get_runtime_settings()
    tz = ZoneInfo(runtime.timezone)
    return datetime.now(tz).date()


async def _today_iso() -> str:
    return (await _today_local()).isoformat()


def _diary_relative_path(date_iso: str) -> str:
    return f"{VAULT_FOLDERS['diary']}/{date_iso}.md"


def _extract_section_content(markdown: str, section_title: str) -> str:
    heading_pattern = rf"(?m)^## {re.escape(section_title)}\n"
    heading_match = re.search(heading_pattern, markdown)
    if not heading_match:
        return ""
    start = heading_match.end()
    next_heading = re.search(r"(?m)^## ", markdown[start:])
    end = start + next_heading.start() if next_heading else len(markdown)
    return markdown[start:end].strip()


def _replace_section_content(markdown: str, section_title: str, new_text: str) -> str:
    heading_pattern = rf"(?m)^## {re.escape(section_title)}\n"
    heading_match = re.search(heading_pattern, markdown)
    if not heading_match:
        raise ValueError(f"Раздел '{section_title}' не найден")
    start = heading_match.end()
    next_heading = re.search(r"(?m)^## ", markdown[start:])
    end = start + next_heading.start() if next_heading else len(markdown)

    replacement = f"{new_text.strip()}\n\n"
    tail = markdown[end:]
    if tail.startswith("\n"):
        tail = tail.lstrip("\n")
    return f"{markdown[:start]}{replacement}{tail}"


@owner_only
async def diary_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа в дневник по кнопке меню или команде."""
    if not update.effective_message:
        return ConversationHandler.END

    today = await _today_local()
    async with SessionLocal() as session:
        existing = await get_diary_entry_by_date(session, today)

    if existing:
        context.user_data["diary_path"] = existing.obsidian_path
        await update.effective_message.reply_text(
            "Запись за сегодня уже есть. Что делаем?",
            reply_markup=get_diary_existing_entry_keyboard(),
        )
        return DIARY_ACTION

    context.user_data["diary_path"] = _diary_relative_path(await _today_iso())
    await update.effective_message.reply_text(
        "Выбери настроение за сегодня:",
        reply_markup=get_diary_mood_keyboard(),
    )
    return DIARY_MOOD


@owner_only
async def diary_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает действия по уже существующей записи дня."""
    if not update.callback_query:
        return DIARY_ACTION
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data == "diary:show":
        path = context.user_data.get("diary_path", _diary_relative_path(await _today_iso()))
        obsidian = ObsidianService()
        try:
            content = await obsidian.read_markdown(path)
            await edit_or_send(update, context, content[:3500], reply_markup=get_diary_existing_entry_keyboard())
        except Exception:
            logger.error("Ошибка чтения дневника", exc_info=True)
            await edit_or_send(update, context, "Не удалось прочитать запись дневника.")
        return ConversationHandler.END

    if data == "diary:edit":
        await edit_or_send(
            update,
            context,
            "Какой раздел хочешь отредактировать?",
            reply_markup=get_diary_edit_sections_keyboard(),
        )
        return DIARY_EDIT_CHOOSE_SECTION

    if data == "diary:back":
        await edit_or_send(update, context, "Возвращаю в главное меню.")
        await query.message.reply_text("Главное меню", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    return DIARY_ACTION


@owner_only
async def diary_edit_choose_section(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор конкретного раздела дневника для редактирования."""
    if not update.callback_query:
        return DIARY_EDIT_CHOOSE_SECTION
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "diary" or parts[1] != "edit_section":
        await edit_or_send(update, context, "Не удалось определить раздел. Выбери снова.")
        return DIARY_EDIT_CHOOSE_SECTION

    section_key = parts[2]
    section_title = DIARY_SECTIONS.get(section_key)
    if not section_title:
        await edit_or_send(update, context, "Неизвестный раздел.")
        return DIARY_EDIT_CHOOSE_SECTION

    path = context.user_data.get("diary_path", _diary_relative_path(await _today_iso()))
    obsidian = ObsidianService()
    try:
        content = await obsidian.read_markdown(path)
        current = _extract_section_content(content, section_title)
    except Exception:
        logger.error("Ошибка чтения раздела дневника", exc_info=True)
        await edit_or_send(update, context, "Не удалось прочитать дневник для редактирования.")
        return ConversationHandler.END

    context.user_data["diary_edit_section_key"] = section_key
    context.user_data["diary_edit_section_title"] = section_title
    shown = current if current else "(раздел пока пуст)"
    await edit_or_send(
        update,
        context,
        f'Текущее содержимое раздела "{section_title}". Отправь новый текст для замены:\n\n{shown[:2500]}'
    )
    return DIARY_EDIT_INPUT_TEXT


@owner_only
async def diary_edit_input_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Замена содержимого выбранного раздела дневника."""
    if not update.effective_message or not update.effective_message.text:
        return DIARY_EDIT_INPUT_TEXT

    section_title = context.user_data.get("diary_edit_section_title")
    if not section_title:
        await update.effective_message.reply_text("Секция не выбрана. Начни редактирование заново.")
        return ConversationHandler.END

    path = context.user_data.get("diary_path", _diary_relative_path(await _today_iso()))
    new_text = update.effective_message.text.strip()
    obsidian = ObsidianService()
    try:
        content = await obsidian.read_markdown(path)
        updated = _replace_section_content(content, section_title, new_text)
        result = await obsidian.write_markdown(path, updated)
    except Exception:
        logger.error("Ошибка обновления раздела дневника", exc_info=True)
        await update.effective_message.reply_text("Не удалось обновить раздел.")
        return ConversationHandler.END

    sync_note = "✅ Sync в Dropbox выполнен." if result.synced else f"⚠️ Sync не выполнен: {result.sync_error}"
    await update.effective_message.reply_text(
        f'✅ Раздел "{section_title}" обновлён\n{sync_note}',
        reply_markup=get_main_menu_keyboard(),
    )
    context.user_data.pop("diary_edit_section_key", None)
    context.user_data.pop("diary_edit_section_title", None)
    return ConversationHandler.END


@owner_only
async def diary_mood(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет настроение и переходит к первому вопросу."""
    if not update.effective_message or not update.effective_message.text:
        return DIARY_MOOD
    mood = update.effective_message.text.strip()
    if mood not in DIARY_MOODS:
        await update.effective_message.reply_text("Выбери настроение кнопкой.", reply_markup=get_diary_mood_keyboard())
        return DIARY_MOOD

    context.user_data["diary_mood"] = mood
    await update.effective_message.reply_text("🌅 Как прошёл день?")
    return DIARY_DAY


@owner_only
async def diary_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет блок 'Как прошёл день'."""
    if not update.effective_message or not update.effective_message.text:
        return DIARY_DAY
    context.user_data["diary_day_text"] = update.effective_message.text.strip()
    await update.effective_message.reply_text("✅ Что сделал сегодня?")
    return DIARY_DONE


@owner_only
async def diary_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет блок 'Что сделал'."""
    if not update.effective_message or not update.effective_message.text:
        return DIARY_DONE
    context.user_data["diary_done_text"] = update.effective_message.text.strip()
    await update.effective_message.reply_text("💭 Мысли и идеи?")
    return DIARY_IDEAS


@owner_only
async def diary_ideas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет блок 'Мысли и идеи'."""
    if not update.effective_message or not update.effective_message.text:
        return DIARY_IDEAS
    context.user_data["diary_ideas_text"] = update.effective_message.text.strip()
    await update.effective_message.reply_text("🎯 Планы на завтра?")
    return DIARY_TOMORROW


@owner_only
async def diary_tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Финализирует запись дневника и сохраняет в файл/БД."""
    if not update.effective_message or not update.effective_message.text:
        return DIARY_TOMORROW
    context.user_data["diary_tomorrow_text"] = update.effective_message.text.strip()

    date_iso = await _today_iso()
    path = context.user_data.get("diary_path", _diary_relative_path(date_iso))
    mood = context.user_data.get("diary_mood", "😐")
    day_text = context.user_data.get("diary_day_text", "")
    done_text = context.user_data.get("diary_done_text", "")
    ideas_text = context.user_data.get("diary_ideas_text", "")
    tomorrow_text = context.user_data.get("diary_tomorrow_text", "")

    markdown = render_diary_markdown(
        date_iso=date_iso,
        mood=mood,
        day_text=day_text,
        done_text=done_text,
        ideas_text=ideas_text,
        tomorrow_text=tomorrow_text,
    )
    obsidian = ObsidianService()
    result = await obsidian.write_markdown(path, markdown)

    today = await _today_local()
    async with SessionLocal() as session:
        existing = await get_diary_entry_by_date(session, today)
        if not existing:
            try:
                await create_diary_entry(session, today, path)
            except IntegrityError:
                logger.error("Ошибка создания записи дневника в БД", exc_info=True)
                await session.rollback()

    sync_note = "✅ Sync в Dropbox выполнен." if result.synced else f"⚠️ Sync не выполнен: {result.sync_error}"
    await update.effective_message.reply_text(
        f"Дневник сохранён за {date_iso}.\n{sync_note}",
        reply_markup=get_main_menu_keyboard(),
    )

    for key in (
        "diary_path",
        "diary_mood",
        "diary_day_text",
        "diary_done_text",
        "diary_ideas_text",
        "diary_tomorrow_text",
    ):
        context.user_data.pop(key, None)
    return ConversationHandler.END


@owner_only
async def diary_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет диалог дневника."""
    if update.effective_message:
        await update.effective_message.reply_text(
            "Операция отменена. Возвращаю в главное меню.",
            reply_markup=get_main_menu_keyboard(),
        )
    return ConversationHandler.END


def register_diary_handlers(application: Application) -> None:
    """Регистрирует ConversationHandler для дневника."""
    conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r".*Дневник$"), diary_entry),
            CommandHandler("diary", diary_entry),
        ],
        states={
            DIARY_ACTION: [CallbackQueryHandler(diary_action_callback, pattern=r"^diary:")],
            DIARY_MOOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_mood)],
            DIARY_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_day)],
            DIARY_DONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_done)],
            DIARY_IDEAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_ideas)],
            DIARY_TOMORROW: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_tomorrow)],
            DIARY_EDIT_CHOOSE_SECTION: [CallbackQueryHandler(diary_edit_choose_section, pattern=r"^diary:edit_section:")],
            DIARY_EDIT_INPUT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_edit_input_text)],
        },
        fallbacks=[CommandHandler("cancel", diary_cancel)],
        per_chat=True,
        per_user=True,
    )
    application.add_handler(conversation)
