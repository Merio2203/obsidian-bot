"""Хендлеры раздела проектов."""

from __future__ import annotations

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

from bot.database import SessionLocal
from bot.database.crud import (
    create_project,
    get_project_by_id,
    get_project_by_name,
    get_projects,
    update_project_status,
)
from bot.services.obsidian_service import ObsidianService
from bot.utils.decorators import owner_only
from bot.utils.formatters import render_project_overview_markdown
from bot.utils.keyboards import (
    get_main_menu_keyboard,
    get_project_actions_keyboard,
    get_projects_menu_keyboard,
    get_project_status_keyboard,
)

logger = logging.getLogger(__name__)

PROJECT_MENU, CREATE_NAME, CREATE_DESCRIPTION, CREATE_STACK, CREATE_REPO = range(5)

STATUS_MAP = {
    "active": "🟡 Активный",
    "paused": "⏸ На паузе",
    "done": "🟢 Завершён",
}


def _safe_project_dir_name(name: str) -> str:
    clean = re.sub(r"[\\/:*?\"<>|]", "", name).strip()
    clean = re.sub(r"\s+", " ", clean)
    return clean or "Новый проект"


def _project_text(name: str, status: str, stack: str, repo_url: str | None, obsidian_path: str) -> str:
    return (
        f"📁 <b>{name}</b>\n"
        f"Статус: {status}\n"
        f"Стек: {stack or 'Не указан'}\n"
        f"Репозиторий: {repo_url or 'Не указан'}\n"
        f"Файл: <code>{obsidian_path}</code>"
    )


@owner_only
async def projects_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа в раздел проектов по кнопке меню."""
    if not update.effective_message:
        return ConversationHandler.END
    await update.effective_message.reply_text(
        "Раздел проектов.\nВыберите действие:",
        reply_markup=get_projects_menu_keyboard(),
    )
    return PROJECT_MENU


@owner_only
async def projects_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка inline-кнопок меню проектов."""
    if not update.callback_query:
        return PROJECT_MENU
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if data == "projects:create":
        await query.message.reply_text("Введите название проекта:")
        return CREATE_NAME

    if data == "projects:list":
        await _send_projects_list(query.message, include_hint=False)
        return PROJECT_MENU

    if data == "projects:back":
        await query.message.reply_text(
            "Возвращаю в главное меню.",
            reply_markup=get_main_menu_keyboard(),
        )
        return ConversationHandler.END

    if data.startswith("projects:open:"):
        project_id = int(data.split(":")[-1])
        await _send_project_card(query.message, project_id)
        return PROJECT_MENU

    if data.startswith("projects:status:"):
        project_id = int(data.split(":")[-1])
        await query.message.reply_text(
            "Выберите новый статус:",
            reply_markup=get_project_status_keyboard(project_id),
        )
        return PROJECT_MENU

    if data.startswith("projects:set_status:"):
        _, _, _, project_id_raw, status_key = data.split(":", 4)
        project_id = int(project_id_raw)
        status = STATUS_MAP.get(status_key)
        if not status:
            await query.message.reply_text("Неизвестный статус.")
            return PROJECT_MENU
        await _set_project_status(query.message, project_id, status)
        return PROJECT_MENU

    if data.startswith("projects:archive:"):
        project_id = int(data.split(":")[-1])
        await _set_project_status(query.message, project_id, "🗄 Архив")
        return PROJECT_MENU

    if data.startswith("projects:tasks:"):
        await query.message.reply_text("Раздел задач проекта подключим следующим шагом.")
        return PROJECT_MENU

    return PROJECT_MENU


@owner_only
async def create_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет название проекта и переходит к описанию."""
    if not update.effective_message or not update.effective_message.text:
        return CREATE_NAME
    context.user_data["project_name"] = update.effective_message.text.strip()
    await update.effective_message.reply_text("Введите краткое описание проекта:")
    return CREATE_DESCRIPTION


@owner_only
async def create_project_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет описание проекта и переходит к стеку."""
    if not update.effective_message or not update.effective_message.text:
        return CREATE_DESCRIPTION
    context.user_data["project_description"] = update.effective_message.text.strip()
    await update.effective_message.reply_text(
        "Введите стек технологий через запятую (например: Python, FastAPI, PostgreSQL):"
    )
    return CREATE_STACK


@owner_only
async def create_project_stack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет стек проекта и запрашивает ссылку на репозиторий."""
    if not update.effective_message or not update.effective_message.text:
        return CREATE_STACK
    context.user_data["project_stack"] = update.effective_message.text.strip()
    await update.effective_message.reply_text(
        "Отправьте ссылку на GitHub репозиторий или '-' если ссылки нет:"
    )
    return CREATE_REPO


@owner_only
async def create_project_repo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Финализирует создание проекта в Obsidian и БД."""
    if not update.effective_message or not update.effective_message.text:
        return CREATE_REPO

    repo_raw = update.effective_message.text.strip()
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

    project_dir = _safe_project_dir_name(name)
    overview_relative = Path("📁 Проекты") / project_dir / "📋 Обзор.md"
    markdown = render_project_overview_markdown(
        title=name,
        description=description or "Описание пока не добавлено.",
        stack_items=stack_items,
        repo_url=repo_url,
    )

    obsidian = ObsidianService()
    write_result = await obsidian.write_markdown(overview_relative, markdown)

    try:
        async with SessionLocal() as session:
            project = await create_project(
                session=session,
                name=name,
                description=description,
                stack=stack_db,
                repo_url=repo_url,
                obsidian_path=str(overview_relative),
            )
    except IntegrityError:
        logger.warning("Проект с именем '%s' уже существует", name)
        await update.effective_message.reply_text(
            "Проект с таким названием уже существует. Используйте другое имя."
        )
        return ConversationHandler.END
    finally:
        context.user_data.pop("project_name", None)
        context.user_data.pop("project_description", None)
        context.user_data.pop("project_stack", None)

    sync_note = (
        "✅ Синхронизация с Dropbox выполнена."
        if write_result.synced
        else f"⚠️ Проект создан, но sync не выполнен: {write_result.sync_error}"
    )
    await update.effective_message.reply_text(
        f"Проект создан:\n\n{_project_text(project.name, project.status, project.stack, project.repo_url, project.obsidian_path)}\n\n{sync_note}",
        parse_mode="HTML",
        reply_markup=get_projects_menu_keyboard(),
    )
    return PROJECT_MENU


@owner_only
async def cancel_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Прерывает диалог раздела проектов."""
    if update.effective_message:
        await update.effective_message.reply_text(
            "Операция отменена. Возвращаю в главное меню.",
            reply_markup=get_main_menu_keyboard(),
        )
    return ConversationHandler.END


async def _send_projects_list(message, include_hint: bool = True) -> None:  # type: ignore[no-untyped-def]
    async with SessionLocal() as session:
        projects = await get_projects(session)

    if not projects:
        await message.reply_text("Пока нет проектов. Нажмите «➕ Создать проект».")
        return

    buttons = [
        [InlineKeyboardButton(f"{project.status} {project.name}", callback_data=f"projects:open:{project.id}")]
        for project in projects
    ]
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="projects:back")])
    text = "Список проектов:"
    if include_hint:
        text += "\nВыберите проект из списка."
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def _send_project_card(message, project_id: int) -> None:  # type: ignore[no-untyped-def]
    async with SessionLocal() as session:
        project = await get_project_by_id(session, project_id)
    if not project:
        await message.reply_text("Проект не найден.")
        return
    await message.reply_text(
        _project_text(project.name, project.status, project.stack, project.repo_url, project.obsidian_path),
        parse_mode="HTML",
        reply_markup=get_project_actions_keyboard(project.id),
    )


async def _set_project_status(message, project_id: int, status: str) -> None:  # type: ignore[no-untyped-def]
    async with SessionLocal() as session:
        project = await get_project_by_id(session, project_id)
        if not project:
            await message.reply_text("Проект не найден.")
            return
        await update_project_status(session, project, status)
    await message.reply_text(f"Статус проекта обновлён: {status}")
    await _send_project_card(message, project_id)


def register_projects_handlers(application: Application) -> None:
    """Регистрирует ConversationHandler раздела проектов."""
    conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r".*Проекты$"), projects_entry),
            CommandHandler("projects", projects_entry),
        ],
        states={
            PROJECT_MENU: [
                CallbackQueryHandler(projects_menu_callback, pattern=r"^projects:"),
            ],
            CREATE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_project_name)],
            CREATE_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_project_description)],
            CREATE_STACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_project_stack)],
            CREATE_REPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_project_repo)],
        },
        fallbacks=[CommandHandler("cancel", cancel_projects)],
        per_chat=True,
        per_user=True,
    )
    application.add_handler(conversation)
