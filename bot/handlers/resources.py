"""Хендлеры раздела ресурсов (статьи и YouTube)."""

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
from bot.database.crud import create_resource
from bot.services.ai_service import AIService
from bot.services.obsidian_service import ObsidianService
from bot.services.parser_service import ParserService
from bot.utils.decorators import owner_only
from bot.utils.formatters import render_resource_markdown
from bot.utils.helpers import (
    ask_for_input,
    edit_or_send,
    handle_unexpected_menu_button,
    universal_cancel_handler,
)
from bot.utils.keyboards import (
    MAIN_MENU_BUTTONS_REGEX,
    get_main_menu_keyboard,
    get_main_reply_keyboard,
    get_resources_reply_keyboard,
)

logger = logging.getLogger(__name__)

RESOURCE_URL = 0


def _normalize_tags(raw_tags: str) -> list[str]:
    tags = []
    for part in raw_tags.split(","):
        token = part.strip().lower().replace(" ", "-")
        if token.startswith("#"):
            token = token[1:]
        if token:
            tags.append(token)
    deduped: list[str] = []
    for tag in tags:
        if tag not in deduped:
            deduped.append(tag)
    return deduped[:7]


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
    return links[:8]


def _extract_key_points(summary_text: str) -> list[str]:
    points = []
    for line in summary_text.splitlines():
        row = line.strip()
        if row.startswith("-"):
            points.append(row.lstrip("- ").strip())
    if points:
        return points[:6]
    compact = [s.strip() for s in summary_text.split(".") if s.strip()]
    return compact[:4]


def _action_keyboard(resource_id: int, resource_type: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ В задачу", callback_data=f"resources:to_task:{resource_id}")],
            [InlineKeyboardButton("📁 В проект", callback_data=f"resources:to_project:{resource_id}")],
            [InlineKeyboardButton(f"ℹ️ Тип: {resource_type}", callback_data="resources:noop")],
        ]
    )


@owner_only
async def resources_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Старт раздела ресурсов."""
    if not update.effective_message:
        return ConversationHandler.END
    await update.effective_message.reply_text("📚 Раздел ресурсов", reply_markup=get_resources_reply_keyboard())
    await ask_for_input(update, context, "Отправь URL статьи или YouTube-видео.", state=RESOURCE_URL)
    return RESOURCE_URL


@owner_only
async def resources_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает URL ресурса и сохраняет его."""
    if not update.effective_message or not update.effective_message.text:
        return RESOURCE_URL

    url = update.effective_message.text.strip()
    if url == "◀️ Назад":
        await update.effective_message.reply_text("Главное меню:", reply_markup=get_main_reply_keyboard())
        return ConversationHandler.END

    if not (url.startswith("http://") or url.startswith("https://")):
        await update.effective_message.reply_text("Нужна корректная ссылка (http/https).")
        return RESOURCE_URL

    parser = ParserService()
    ai = AIService(SessionLocal)
    obsidian = ObsidianService()
    existing_links = await obsidian.get_existing_links("all")

    try:
        if parser.is_youtube_url(url):
            meta = await parser.parse_youtube(url)
            summary = await ai.summarize_youtube(meta.title, meta.description, meta.author)
            resource_type = "youtube"
            folder = f"{VAULT_FOLDERS['resources']}/Видео"
            title = meta.title
        else:
            article = await parser.parse_article(url)
            summary = await ai.summarize_article(article.title, article.content)
            resource_type = "article"
            folder = f"{VAULT_FOLDERS['resources']}/Статьи"
            title = article.title
    except Exception:  # noqa: BLE001
        logger.error("Ошибка обработки ресурса", exc_info=True)
        await update.effective_message.reply_text("Не удалось обработать ресурс. Попробуй другую ссылку.")
        return RESOURCE_URL

    try:
        raw_tags = await ai.generate_tags(f"{title}\n{summary}")
        tags = _normalize_tags(raw_tags)
    except Exception:  # noqa: BLE001
        logger.error("Не удалось сгенерировать теги", exc_info=True)
        tags = ["ресурс", "youtube" if resource_type == "youtube" else "статья"]
    try:
        links_payload = await ai.generate_links_for_content(
            content_type="resource",
            text=f"{title}\n{summary}",
            existing_links=existing_links,
        )
        links = _normalize_links(links_payload.get("links"))
    except Exception:
        logger.error("Не удалось сгенерировать links для ресурса", exc_info=True)
        links = []

    key_points = _extract_key_points(summary)
    markdown = render_resource_markdown(
        title=title,
        url=url,
        resource_type=resource_type,
        tags=tags,
        summary=summary,
        key_points=key_points,
        links=links,
    )

    file_name = f"{obsidian.slugify_filename(title)}.md"
    relative_path = f"{folder}/{file_name}"
    write_result = await obsidian.write_markdown(relative_path, markdown)

    async with SessionLocal() as session:
        resource = await create_resource(
            session=session,
            title=title,
            url=url,
            resource_type=resource_type,
            tags=",".join(tags),
            obsidian_path=relative_path,
        )

    sync_note = "✅ Sync в Dropbox выполнен." if write_result.synced else f"⚠️ Sync не выполнен: {write_result.sync_error}"
    await update.effective_message.reply_text(
        f"Ресурс сохранён.\n\nНазвание: {title}\nТип: {resource_type}\nТеги: {', '.join(tags)}\n"
        f"Файл: {resource.obsidian_path}\n\n{sync_note}",
        reply_markup=_action_keyboard(resource.id, resource_type),
    )
    context.user_data.pop("expecting_text_input", None)
    context.user_data.pop("input_state", None)
    await update.effective_message.reply_text("Главное меню:", reply_markup=get_main_reply_keyboard())
    return ConversationHandler.END


@owner_only
async def resources_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка inline-действий после сохранения ресурса."""
    if not update.callback_query:
        return
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 2:
        return
    action = parts[1]
    if action == "noop":
        return
    resource_id = parts[2] if len(parts) > 2 else "?"
    if action == "to_task":
        await edit_or_send(
            update,
            context,
            f"Нажми кнопку ✅ Задачи, чтобы создать задачу по ресурсу #{resource_id}.",
        )
        await query.message.reply_text("Главное меню", reply_markup=get_main_menu_keyboard())
        return
    if action == "to_project":
        await edit_or_send(
            update,
            context,
            f"Нажми кнопку 📁 Проекты, чтобы создать проект по ресурсу #{resource_id}.",
        )
        await query.message.reply_text("Главное меню", reply_markup=get_main_menu_keyboard())
        return


@owner_only
async def resources_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена сценария сохранения ресурса."""
    return await universal_cancel_handler(update, context)


def register_resources_handlers(application: Application) -> None:
    """Регистрирует хендлеры раздела ресурсов."""
    conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r".*Ресурс$"), resources_entry),
            MessageHandler(filters.Regex(r"^➕ Добавить ресурс$"), resources_entry),
            CommandHandler("resource", resources_entry),
        ],
        states={
            RESOURCE_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, resources_url)],
        },
        fallbacks=[
            CommandHandler("cancel", resources_cancel),
            CallbackQueryHandler(universal_cancel_handler, pattern=r"^cancel$"),
            MessageHandler(filters.TEXT & filters.Regex(MAIN_MENU_BUTTONS_REGEX), handle_unexpected_menu_button),
        ],
        per_chat=True,
        per_user=True,
    )
    application.add_handler(conversation)
    application.add_handler(CallbackQueryHandler(resources_action_callback, pattern=r"^resources:"))
