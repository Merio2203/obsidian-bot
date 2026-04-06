"""Хендлеры быстрых заметок: идеи и входящие."""

from __future__ import annotations

import logging

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

from bot.database import SessionLocal
from bot.database.crud import create_note
from bot.services.ai_service import AIService
from bot.services.obsidian_service import ObsidianService
from bot.utils.decorators import owner_only
from bot.utils.formatters import render_note_markdown
from bot.utils.keyboards import get_main_menu_keyboard

logger = logging.getLogger(__name__)

NOTE_TEXT = 0


def _extract_title(text: str) -> str:
    line = text.strip().splitlines()[0] if text.strip() else "Новая заметка"
    short = line[:60].strip()
    return short or "Новая заметка"


def _normalize_tags(raw_tags: str) -> list[str]:
    tags = []
    for part in raw_tags.split(","):
        token = part.strip().lower().replace(" ", "-")
        if not token:
            continue
        if token.startswith("#"):
            token = token[1:]
        tags.append(token)
    deduped: list[str] = []
    for tag in tags:
        if tag not in deduped:
            deduped.append(tag)
    return deduped[:5]


def _action_keyboard(note_type: str, payload: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Превратить в задачу", callback_data=f"notes:to_task:{note_type}:{payload}")],
            [InlineKeyboardButton("📁 Превратить в проект", callback_data=f"notes:to_project:{note_type}:{payload}")],
        ]
    )


@owner_only
async def idea_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Старт создания идеи."""
    if not update.effective_message:
        return ConversationHandler.END
    context.user_data["note_type"] = "idea"
    await update.effective_message.reply_text("Отправь текст идеи одним сообщением.")
    return NOTE_TEXT


@owner_only
async def inbox_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Старт создания входящей заметки."""
    if not update.effective_message:
        return ConversationHandler.END
    context.user_data["note_type"] = "inbox"
    await update.effective_message.reply_text("Отправь входящую заметку одним сообщением.")
    return NOTE_TEXT


@owner_only
async def save_note_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет идею/входящую заметку в Obsidian и БД."""
    if not update.effective_message or not update.effective_message.text:
        return NOTE_TEXT

    content = update.effective_message.text.strip()
    note_type = context.user_data.get("note_type", "inbox")
    if not content:
        await update.effective_message.reply_text("Текст пустой. Отправь заметку ещё раз.")
        return NOTE_TEXT

    title = _extract_title(content)
    folder = "💡 Идеи" if note_type == "idea" else "📥 Входящие"

    ai = AIService(SessionLocal)
    try:
        raw_tags = await ai.generate_tags(content)
        tags = _normalize_tags(raw_tags)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось получить AI-теги: %s", exc)
        tags = ["заметка", "входящие" if note_type == "inbox" else "идея"]

    obsidian = ObsidianService()
    filename = f"{obsidian.sanitize_filename(title)}.md"
    relative_path = f"{folder}/{filename}"
    markdown = render_note_markdown(
        title=title,
        note_type=note_type,
        tags=tags,
        content=content,
    )
    result = await obsidian.write_markdown(relative_path, markdown)

    async with SessionLocal() as session:
        note = await create_note(
            session=session,
            title=title,
            note_type=note_type,
            content=content,
            tags=",".join(tags),
            obsidian_path=relative_path,
        )

    sync_note = "✅ Sync в Dropbox выполнен." if result.synced else f"⚠️ Sync не выполнен: {result.sync_error}"
    await update.effective_message.reply_text(
        f"Заметка сохранена.\n\nТип: {'Идея' if note_type == 'idea' else 'Входящие'}\n"
        f"Название: {note.title}\n"
        f"Теги: {', '.join(tags)}\n"
        f"Файл: {note.obsidian_path}\n\n{sync_note}",
        reply_markup=_action_keyboard(note_type, str(note.id)),
    )
    return ConversationHandler.END


@owner_only
async def notes_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает быстрые действия после сохранения заметки."""
    if not update.callback_query:
        return
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    parts = data.split(":")
    if len(parts) != 4:
        await query.message.reply_text("Не удалось обработать действие.")
        return
    _, action, note_type, note_id = parts

    if action == "to_task":
        await query.message.reply_text(
            f"Открываю сценарий задачи для заметки #{note_id}. Нажми кнопку ✅ Задачи и создай задачу.",
            reply_markup=get_main_menu_keyboard(),
        )
        return
    if action == "to_project":
        await query.message.reply_text(
            f"Открываю сценарий проекта для заметки #{note_id}. Нажми кнопку 📁 Проекты и создай проект.",
            reply_markup=get_main_menu_keyboard(),
        )
        return


@owner_only
async def notes_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена создания заметки."""
    if update.effective_message:
        await update.effective_message.reply_text(
            "Операция отменена. Возвращаю в главное меню.",
            reply_markup=get_main_menu_keyboard(),
        )
    return ConversationHandler.END


def register_notes_handlers(application: Application) -> None:
    """Регистрирует хендлеры идей и входящих заметок."""
    conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r".*Идея$"), idea_entry),
            MessageHandler(filters.Regex(r".*Входящие$"), inbox_entry),
            CommandHandler("idea", idea_entry),
            CommandHandler("inbox", inbox_entry),
        ],
        states={
            NOTE_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_note_text)],
        },
        fallbacks=[CommandHandler("cancel", notes_cancel)],
        per_chat=True,
        per_user=True,
    )
    application.add_handler(conversation)
    application.add_handler(CallbackQueryHandler(notes_action_callback, pattern=r"^notes:"))
