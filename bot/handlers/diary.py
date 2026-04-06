"""Хендлеры раздела дневника."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
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

from bot.config import settings
from bot.database import SessionLocal
from bot.database.crud import create_diary_entry, get_diary_entry_by_date
from bot.services.obsidian_service import ObsidianService
from bot.utils.decorators import owner_only
from bot.utils.formatters import render_diary_append_block, render_diary_markdown
from bot.utils.keyboards import get_diary_mood_keyboard, get_main_menu_keyboard

logger = logging.getLogger(__name__)

DIARY_ACTION, DIARY_MOOD, DIARY_DAY, DIARY_DONE, DIARY_IDEAS, DIARY_TOMORROW = range(6)

DIARY_MOODS = {"😊", "😐", "😔", "😤", "🤩"}


def _today_local() -> datetime.date:
    tz = ZoneInfo(settings.timezone)
    return datetime.now(tz).date()


def _today_iso() -> str:
    return _today_local().isoformat()


def _diary_relative_path(date_iso: str) -> str:
    return f"📓 Дневник/{date_iso}.md"


def _build_existing_diary_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📖 Показать", callback_data="diary:show")],
            [InlineKeyboardButton("➕ Дополнить", callback_data="diary:append")],
            [InlineKeyboardButton("✍️ Перезаписать", callback_data="diary:rewrite")],
            [InlineKeyboardButton("◀️ Назад", callback_data="diary:back")],
        ]
    )


@owner_only
async def diary_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа в дневник по кнопке меню или команде."""
    if not update.effective_message:
        return ConversationHandler.END

    today = _today_local()
    async with SessionLocal() as session:
        existing = await get_diary_entry_by_date(session, today)

    context.user_data["diary_mode"] = "new"
    if existing:
        context.user_data["diary_mode"] = "append"
        context.user_data["diary_path"] = existing.obsidian_path
        await update.effective_message.reply_text(
            "Запись за сегодня уже есть. Что делаем?",
            reply_markup=_build_existing_diary_keyboard(),
        )
        return DIARY_ACTION

    context.user_data["diary_path"] = _diary_relative_path(_today_iso())
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
        path = context.user_data.get("diary_path", _diary_relative_path(_today_iso()))
        obsidian = ObsidianService()
        try:
            content = await obsidian.read_markdown(path)
            await query.message.reply_text(content[:3500], reply_markup=get_main_menu_keyboard())
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка чтения дневника: %s", exc)
            await query.message.reply_text("Не удалось прочитать запись дневника.", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    if data == "diary:append":
        context.user_data["diary_mode"] = "append"
        await query.message.reply_text("Отлично, дополним запись. Выбери настроение:", reply_markup=get_diary_mood_keyboard())
        return DIARY_MOOD

    if data == "diary:rewrite":
        context.user_data["diary_mode"] = "rewrite"
        await query.message.reply_text("Перезаписываем запись. Выбери настроение:", reply_markup=get_diary_mood_keyboard())
        return DIARY_MOOD

    if data == "diary:back":
        await query.message.reply_text("Возвращаю в главное меню.", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    return DIARY_ACTION


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
    await update.effective_message.reply_text("🌅 Как прошёл день?", reply_markup=ReplyKeyboardRemove())
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

    date_iso = _today_iso()
    path = context.user_data.get("diary_path", _diary_relative_path(date_iso))
    mode = context.user_data.get("diary_mode", "new")
    mood = context.user_data.get("diary_mood", "😐")
    day_text = context.user_data.get("diary_day_text", "")
    done_text = context.user_data.get("diary_done_text", "")
    ideas_text = context.user_data.get("diary_ideas_text", "")
    tomorrow_text = context.user_data.get("diary_tomorrow_text", "")

    obsidian = ObsidianService()
    if mode == "append":
        append_block = render_diary_append_block(
            mood=mood,
            day_text=day_text,
            done_text=done_text,
            ideas_text=ideas_text,
            tomorrow_text=tomorrow_text,
        )
        result = await obsidian.update_markdown(path, append_block)
    else:
        markdown = render_diary_markdown(
            date_iso=date_iso,
            mood=mood,
            day_text=day_text,
            done_text=done_text,
            ideas_text=ideas_text,
            tomorrow_text=tomorrow_text,
        )
        result = await obsidian.write_markdown(path, markdown)

    if mode in ("new", "rewrite"):
        async with SessionLocal() as session:
            existing = await get_diary_entry_by_date(session, _today_local())
            if not existing:
                try:
                    await create_diary_entry(session, _today_local(), path)
                except IntegrityError:
                    await session.rollback()

    sync_note = "✅ Sync в Dropbox выполнен." if result.synced else f"⚠️ Sync не выполнен: {result.sync_error}"
    await update.effective_message.reply_text(
        f"Дневник сохранён за {date_iso}.\n{sync_note}",
        reply_markup=get_main_menu_keyboard(),
    )

    for key in (
        "diary_mode",
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
        },
        fallbacks=[CommandHandler("cancel", diary_cancel)],
        per_chat=True,
        per_user=True,
    )
    application.add_handler(conversation)
