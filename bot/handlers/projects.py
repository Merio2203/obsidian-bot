"""Хендлеры раздела проектов."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from sqlalchemy.exc import IntegrityError
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
from bot.database.crud import create_project, get_project_by_name
from bot.services.obsidian_service import ObsidianService, sync_db_with_vault
from bot.utils.decorators import owner_only
from bot.utils.formatters import render_project_overview_markdown
from bot.utils.helpers import (
    ask_for_input,
    edit_or_send,
    handle_unexpected_menu_button,
    universal_cancel_handler,
)
from bot.utils.keyboards import (
    MAIN_MENU_BUTTONS_REGEX,
    get_default_skip_keyboard,
    get_main_menu_keyboard,
    get_projects_reply_keyboard,
)

logger = logging.getLogger(__name__)

PROJECT_MENU, CREATE_NAME, CREATE_DESCRIPTION, CREATE_STACK, CREATE_REPO = range(5)

STATUS_MAP = {
    "active": "🟡 Активный",
    "paused": "⏸ На паузе",
    "done": "🟢 Завершён",
}


def _project_text(name: str, status: str, stack: str, repo_url: str | None, obsidian_path: str) -> str:
    return (
        f"📁 <b>{name}</b>\n"
        f"Статус: {status}\n"
        f"Стек: {stack or 'Не указан'}\n"
        f"Репозиторий: {repo_url or 'Не указан'}\n"
        f"Файл: <code>{obsidian_path}</code>"
    )


def _build_project_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Задачи проекта", callback_data="projects:tasks_current")],
            [InlineKeyboardButton("🔄 Изменить статус", callback_data="projects:status_current")],
            [InlineKeyboardButton("🗃 Архивировать", callback_data="projects:archive_current")],
            [InlineKeyboardButton("⬅️ К списку", callback_data="projects:list")],
        ]
    )


def _build_status_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🟡 Активный", callback_data="projects:set_status:active")],
            [InlineKeyboardButton("⏸ На паузе", callback_data="projects:set_status:paused")],
            [InlineKeyboardButton("🟢 Завершён", callback_data="projects:set_status:done")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="projects:list")],
        ]
    )


def _extract_yaml_value(content: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else ""


@owner_only
async def projects_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа в раздел проектов по кнопке меню."""
    if not update.effective_message:
        return ConversationHandler.END
    await update.effective_message.reply_text("📁 Раздел проектов", reply_markup=get_projects_reply_keyboard())
    await edit_or_send(
        update,
        context,
        "Раздел проектов.\nВыберите действие:",
    )
    return PROJECT_MENU


@owner_only
async def projects_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка inline-кнопок меню проектов."""
    if not update.callback_query:
        return PROJECT_MENU
    try:
        await update.callback_query.answer()
    except Exception:
        logger.debug("Не удалось ответить на callback в projects_menu_callback", exc_info=True)
    data = update.callback_query.data or ""

    if data == "projects:create":
        await ask_for_input(update, context, "📁 Введите название проекта:", state=CREATE_NAME)
        return CREATE_NAME

    if data == "projects:list":
        await _send_projects_list(update, context, include_hint=False)
        return PROJECT_MENU

    if data == "projects:back":
        await update.callback_query.answer("Возвращаю в главное меню.", show_alert=False)
        await edit_or_send(
            update,
            context,
            "Главное меню",
            reply_markup=None,
        )
        if update.callback_query.message:
            await update.callback_query.message.reply_text(
                "Главное меню",
                reply_markup=get_main_menu_keyboard(),
            )
        return ConversationHandler.END

    if data.startswith("projects:open:"):
        idx = data.split(":")[-1]
        await _send_project_card(update, context, idx)
        return PROJECT_MENU

    if data == "projects:repo:skip":
        context.user_data["project_repo_raw"] = "-"
        if update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_text("Пропускаю ссылку на репозиторий.")
        return await create_project_repo(update, context)

    if data == "projects:status_current":
        await edit_or_send(update, context, "Выберите новый статус:", reply_markup=_build_status_keyboard())
        return PROJECT_MENU

    if data.startswith("projects:set_status:"):
        status_key = data.split(":")[-1]
        status = STATUS_MAP.get(status_key)
        if not status:
            await update.callback_query.answer("Неизвестный статус", show_alert=True)
            return PROJECT_MENU
        await _set_project_status(update, context, status)
        return PROJECT_MENU

    if data == "projects:archive_current":
        await _set_project_status(update, context, "🗄 Архив")
        return PROJECT_MENU

    if data == "projects:tasks_current":
        await update.callback_query.answer("Раздел задач проекта подключим следующим шагом.", show_alert=False)
        return PROJECT_MENU

    return PROJECT_MENU


@owner_only
async def projects_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка контекстных reply-кнопок раздела проектов."""
    if not update.effective_message or not update.effective_message.text:
        return PROJECT_MENU
    text = update.effective_message.text.strip()
    if text == "➕ Создать проект":
        await ask_for_input(update, context, "📁 Введите название проекта:", state=CREATE_NAME)
        return CREATE_NAME
    if text == "📋 Список проектов":
        await _send_projects_list(update, context, include_hint=False)
        return PROJECT_MENU
    if text == "◀️ Назад":
        await update.effective_message.reply_text("Главное меню", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END
    return PROJECT_MENU


@owner_only
async def create_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет название проекта и переходит к описанию."""
    if not update.effective_message or not update.effective_message.text:
        return CREATE_NAME
    context.user_data["project_name"] = update.effective_message.text.strip()
    await ask_for_input(update, context, "Введите краткое описание проекта:", state=CREATE_DESCRIPTION)
    return CREATE_DESCRIPTION


@owner_only
async def create_project_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет описание проекта и переходит к стеку."""
    if not update.effective_message or not update.effective_message.text:
        return CREATE_DESCRIPTION
    context.user_data["project_description"] = update.effective_message.text.strip()
    await ask_for_input(
        update,
        context,
        "Введите стек технологий через запятую (например: Python, FastAPI, PostgreSQL):",
        state=CREATE_STACK,
    )
    return CREATE_STACK


@owner_only
async def create_project_stack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет стек проекта и запрашивает ссылку на репозиторий."""
    if not update.effective_message or not update.effective_message.text:
        return CREATE_STACK
    context.user_data["project_stack"] = update.effective_message.text.strip()
    await ask_for_input(
        update,
        context,
        "Отправьте ссылку на GitHub репозиторий или '-' если ссылки нет:",
        state=CREATE_REPO,
        inline_keyboard=get_default_skip_keyboard("projects:repo:skip"),
    )
    return CREATE_REPO


@owner_only
async def create_project_repo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Финализирует создание проекта в Obsidian и БД."""
    if not update.effective_message or not update.effective_message.text:
        return CREATE_REPO

    if not context.user_data.get("project_repo_raw"):
        context.user_data["project_repo_raw"] = update.effective_message.text.strip()
    repo_raw = str(context.user_data.get("project_repo_raw", "")).strip()
    context.user_data.pop("project_repo_raw", None)
    repo_url = None if repo_raw == "-" else repo_raw

    name: str = context.user_data.get("project_name", "").strip()
    description: str = context.user_data.get("project_description", "").strip()
    stack_raw: str = context.user_data.get("project_stack", "").strip()
    stack_items = [item.strip() for item in stack_raw.split(",") if item.strip()]
    stack_db = ", ".join(stack_items)

    if not name:
        await update.effective_message.reply_text("Название проекта не задано. Начните заново.")
        return ConversationHandler.END

    async with SessionLocal() as session:
        existing = await get_project_by_name(session, name)
    if existing:
        await update.effective_message.reply_text(
            "Проект с таким названием уже существует. Используйте другое имя."
        )
        return ConversationHandler.END

    obsidian = ObsidianService()
    project_dir = obsidian.sanitize_filename(name)
    overview_relative = obsidian.get_project_overview_relative(name)
    markdown = render_project_overview_markdown(
        title=name,
        description=description or "Описание пока не добавлено.",
        stack_items=stack_items,
        repo_url=repo_url,
    )

    write_result = await obsidian.write_markdown(overview_relative, markdown)
    for subfolder in PROJECT_SUBFOLDERS:
        await asyncio.to_thread(
            (obsidian.vault_path / VAULT_FOLDERS["projects"] / project_dir / subfolder).mkdir,
            parents=True,
            exist_ok=True,
        )

    try:
        async with SessionLocal() as session:
            project = await create_project(
                session=session,
                name=project_dir,
                description=description,
                stack=stack_db,
                repo_url=repo_url,
                obsidian_path=str(overview_relative),
            )
    except IntegrityError:
        logger.warning("Проект с именем '%s' уже существует", project_dir)
        await update.effective_message.reply_text(
            "Проект с таким названием уже существует. Используйте другое имя."
        )
        return ConversationHandler.END
    finally:
        context.user_data.pop("project_name", None)
        context.user_data.pop("project_description", None)
        context.user_data.pop("project_stack", None)
        context.user_data.pop("expecting_text_input", None)
        context.user_data.pop("input_state", None)

    await sync_db_with_vault()
    sync_note = (
        "✅ Синхронизация с Dropbox выполнена."
        if write_result.synced
        else f"⚠️ Проект создан, но sync не выполнен: {write_result.sync_error}"
    )
    await update.effective_message.reply_text(
        f"Проект создан:\n\n{_project_text(project.name, project.status, project.stack, project.repo_url, project.obsidian_path)}\n\n{sync_note}",
        parse_mode="HTML",
    )
    await update.effective_message.reply_text("📁 Раздел проектов", reply_markup=get_projects_reply_keyboard())
    return PROJECT_MENU


@owner_only
async def cancel_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Прерывает диалог раздела проектов."""
    return await universal_cancel_handler(update, context)


async def _send_projects_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    include_hint: bool = True,
) -> None:
    obsidian = ObsidianService()
    projects = await obsidian.get_projects_from_vault()
    await sync_db_with_vault()

    if not projects:
        await edit_or_send(
            update,
            context,
            "Пока нет проектов. Нажмите «➕ Создать проект».",
        )
        return

    context.user_data["projects_index"] = {str(i): p for i, p in enumerate(projects)}
    buttons = [
        [InlineKeyboardButton(f"{p['status']} {p['name']}", callback_data=f"projects:open:{i}")]
        for i, p in enumerate(projects)
    ]
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="projects:back")])
    text = "Список проектов:"
    if include_hint:
        text += "\nВыберите проект из списка."
    await edit_or_send(update, context, text, reply_markup=InlineKeyboardMarkup(buttons))


async def _send_project_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    idx: str,
) -> None:
    index_map: dict[str, dict[str, str]] = context.user_data.get("projects_index", {})
    project = index_map.get(idx)
    if not project:
        await edit_or_send(update, context, "Проект не найден. Обновите список.")
        return

    project_name = project["name"]
    context.user_data["current_project_name"] = project_name

    obsidian = ObsidianService()
    overview_relative = obsidian.get_project_overview_relative(project_name)
    overview_abs = obsidian.vault_path / overview_relative
    stack = ""
    repo_url = ""
    if await asyncio.to_thread(overview_abs.exists):
        content = await asyncio.to_thread(overview_abs.read_text, "utf-8")
        stack = _extract_yaml_value(content, "stack")
        repo_url = _extract_yaml_value(content, "repository")

    await edit_or_send(
        update,
        context,
        _project_text(
            project_name,
            project.get("status", "🟡 Активный"),
            stack,
            repo_url or None,
            str(overview_relative),
        ),
        reply_markup=_build_project_actions_keyboard(),
    )


async def _set_project_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    status: str,
) -> None:
    project_name = context.user_data.get("current_project_name")
    if not project_name:
        await edit_or_send(update, context, "Сначала выберите проект из списка.")
        return

    obsidian = ObsidianService()
    overview_relative = obsidian.get_project_overview_relative(project_name)
    overview_abs = obsidian.vault_path / overview_relative
    if not await asyncio.to_thread(overview_abs.exists):
        await edit_or_send(update, context, "Файл проекта не найден.")
        return

    content = await asyncio.to_thread(overview_abs.read_text, "utf-8")
    if re.search(r"^status:\s*.+$", content, re.MULTILINE):
        updated = re.sub(r"^status:\s*.+$", f"status: {status}", content, flags=re.MULTILINE)
    else:
        updated = content
    await obsidian.write_markdown(overview_relative, updated)
    await sync_db_with_vault()
    await update.callback_query.answer(f"Статус обновлён: {status}", show_alert=False)
    await _send_projects_list(update, context, include_hint=False)


def register_projects_handlers(application: Application) -> None:
    """Регистрирует ConversationHandler раздела проектов."""
    conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r".*Проекты$"), projects_entry),
            MessageHandler(filters.Regex(r"^➕ Создать проект$"), projects_entry),
            CommandHandler("projects", projects_entry),
        ],
        states={
            PROJECT_MENU: [
                CallbackQueryHandler(projects_menu_callback, pattern=r"^projects:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, projects_menu_text),
            ],
            CREATE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_project_name)],
            CREATE_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_project_description)],
            CREATE_STACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_project_stack)],
            CREATE_REPO: [
                CallbackQueryHandler(projects_menu_callback, pattern=r"^projects:repo:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_project_repo),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_projects),
            CallbackQueryHandler(universal_cancel_handler, pattern=r"^cancel$"),
            MessageHandler(filters.TEXT & filters.Regex(MAIN_MENU_BUTTONS_REGEX), handle_unexpected_menu_button),
        ],
        per_chat=True,
        per_user=True,
    )
    application.add_handler(conversation)
