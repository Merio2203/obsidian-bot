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

from bot.config import VAULT_FOLDERS
from bot.database import SessionLocal
from bot.database.crud import create_note
from bot.services.ai_service import AIService
from bot.services.obsidian_service import ObsidianService
from bot.utils.decorators import owner_only
from bot.utils.formatters import render_note_markdown
from bot.utils.helpers import (
    ask_for_input,
    edit_or_send,
    handle_unexpected_menu_button,
    universal_cancel_handler,
)
from bot.utils.keyboards import MAIN_MENU_BUTTONS_REGEX, get_main_menu_keyboard, get_main_reply_keyboard

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


def _normalize_links(raw_links: list[str] | str | None) -> list[str]:
    if raw_links is None:
        return []
    if isinstance(raw_links, str):
        source = [x.strip() for x in raw_links.split(",")]
    else:
        source = [str(x).strip() for x in raw_links]
    links = []
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
    return links[:6]


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
    await ask_for_input(update, context, "💡 Введи текст идеи одним сообщением:", state=NOTE_TEXT)
    return NOTE_TEXT


@owner_only
async def inbox_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Старт создания входящей заметки."""
    if not update.effective_message:
        return ConversationHandler.END
    context.user_data["note_type"] = "inbox"
    await ask_for_input(update, context, "📥 Введи входящую заметку одним сообщением:", state=NOTE_TEXT)
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
    folder = VAULT_FOLDERS["ideas"] if note_type == "idea" else VAULT_FOLDERS["inbox"]

    ai = AIService(SessionLocal)
    obsidian = ObsidianService()
    existing_links = await obsidian.get_existing_links("all")
    try:
        raw_tags = await ai.generate_tags(content)
        tags = _normalize_tags(raw_tags)
    except Exception:  # noqa: BLE001
        logger.error("Не удалось получить AI-теги", exc_info=True)
        tags = ["заметка", "входящие" if note_type == "inbox" else "идея"]
    links: list[str] = []
    try:
        links_payload = await ai.generate_links_for_content(
            content_type="note",
            text=content,
            existing_links=existing_links,
        )
        links = _normalize_links(links_payload.get("links"))
    except Exception:
        logger.error("Не удалось сгенерировать AI-links для заметки", exc_info=True)

    filename = f"{obsidian.slugify_filename(title)}.md"
    relative_path = f"{folder}/{filename}"
    markdown = render_note_markdown(
        title=title,
        note_type=note_type,
        tags=tags,
        links=links,
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
    context.user_data.pop("expecting_text_input", None)
    context.user_data.pop("input_state", None)
    await update.effective_message.reply_text("Главное меню:", reply_markup=get_main_reply_keyboard())
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
        await edit_or_send(update, context, "Не удалось обработать действие.")
        return
    _, action, note_type, note_id = parts

    if action == "to_task":
        await edit_or_send(
            update,
            context,
            f"Открываю сценарий задачи для заметки #{note_id}. Нажми кнопку ✅ Задачи и создай задачу.",
        )
        await query.message.reply_text("Главное меню", reply_markup=get_main_menu_keyboard())
        return
    if action == "to_project":
        await edit_or_send(
            update,
            context,
            f"Открываю сценарий проекта для заметки #{note_id}. Нажми кнопку 📁 Проекты и создай проект.",
        )
        await query.message.reply_text("Главное меню", reply_markup=get_main_menu_keyboard())
        return


@owner_only
async def notes_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена создания заметки."""
    return await universal_cancel_handler(update, context)


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
        fallbacks=[
            CommandHandler("cancel", notes_cancel),
            CallbackQueryHandler(universal_cancel_handler, pattern=r"^cancel$"),
            MessageHandler(filters.TEXT & filters.Regex(MAIN_MENU_BUTTONS_REGEX), handle_unexpected_menu_button),
        ],
        per_chat=True,
        per_user=True,
    )
    application.add_handler(conversation)
    application.add_handler(CallbackQueryHandler(notes_action_callback, pattern=r"^notes:"))
