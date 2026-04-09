"""Хендлеры раздела настроек."""

from __future__ import annotations

import asyncio
import logging
import os

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
from bot.services.obsidian_service import ObsidianService, sync_db_with_vault
from bot.services.settings_service import SettingsPersistenceError, SettingsService
from bot.utils.decorators import owner_only
from bot.utils.keyboards import get_main_menu_keyboard
from bot.utils.logger import LOG_LEVELS, apply_log_level

logger = logging.getLogger(__name__)

SETTINGS_MENU, SETTINGS_TZ_INPUT = range(2)


def _settings_keyboard(log_level: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"📊 Уровень логов: {log_level}", callback_data="settings:log_level")],
            [InlineKeyboardButton("🌍 Изменить timezone", callback_data="settings:set_tz")],
            [InlineKeyboardButton("📓 Переключить напоминание дневника", callback_data="settings:toggle_diary")],
            [InlineKeyboardButton("🌅 Переключить утренний дайджест", callback_data="settings:toggle_digest")],
            [InlineKeyboardButton("🔄 Синхронизировать сейчас", callback_data="settings:sync")],
            [InlineKeyboardButton("♻️ Перезагрузить бота", callback_data="settings:reload")],
            [InlineKeyboardButton("◀️ Назад", callback_data="settings:back")],
        ]
    )


def _settings_text(timezone_name: str, diary_enabled: bool, digest_enabled: bool, log_level: str) -> str:
    diary_state = "ВКЛ" if diary_enabled else "ВЫКЛ"
    digest_state = "ВКЛ" if digest_enabled else "ВЫКЛ"
    return (
        "⚙️ Текущие настройки:\n\n"
        f"- Timezone: {timezone_name}\n"
        f"- Напоминание о дневнике: {diary_state}\n"
        f"- Утренний дайджест: {digest_state}\n"
        f"- Уровень логов: {log_level}"
    )


def _log_levels_keyboard(current_level: str) -> InlineKeyboardMarkup:
    buttons = []
    for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
        mark = "✅ " if level == current_level else ""
        label = {
            "DEBUG": "🔍 DEBUG — всё подряд",
            "INFO": "ℹ️ INFO — основные события",
            "WARNING": "⚠️ WARNING — предупреждения",
            "ERROR": "🔴 ERROR — только ошибки",
        }[level]
        buttons.append([InlineKeyboardButton(f"{mark}{label}", callback_data=f"settings:set_log_level:{level}")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="settings:back_to_settings")])
    return InlineKeyboardMarkup(buttons)


@owner_only
async def settings_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа в настройки."""
    if not update.effective_message:
        return ConversationHandler.END
    service = SettingsService(SessionLocal)
    cfg = await service.get_runtime_settings()
    await update.effective_message.reply_text(
        _settings_text(cfg.timezone, cfg.diary_reminder_enabled, cfg.morning_digest_enabled, cfg.log_level),
        reply_markup=_settings_keyboard(cfg.log_level),
    )
    return SETTINGS_MENU


@owner_only
async def settings_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка кнопок меню настроек."""
    if not update.callback_query:
        return SETTINGS_MENU
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    service = SettingsService(SessionLocal)

    if data == "settings:set_tz":
        await query.message.reply_text("Отправь timezone, например: Europe/Kaliningrad")
        return SETTINGS_TZ_INPUT

    if data == "settings:log_level":
        current = await service.get_log_level()
        await query.message.reply_text(
            "Выберите уровень логирования:",
            reply_markup=_log_levels_keyboard(current),
        )
        return SETTINGS_MENU

    if data.startswith("settings:set_log_level:"):
        level_name = data.split(":")[-1].upper()
        if level_name not in LOG_LEVELS:
            await query.answer("Неизвестный уровень", show_alert=True)
            return SETTINGS_MENU
        try:
            await service.set_log_level(level_name)
        except SettingsPersistenceError as exc:
            await query.message.reply_text(f"⚠️ Не удалось сохранить настройки: {exc}")
            return SETTINGS_MENU
        apply_log_level(level_name)
        await query.answer(f"✅ Уровень логов изменён на {level_name}", show_alert=False)
        cfg = await service.get_runtime_settings()
        await query.message.reply_text(
            _settings_text(cfg.timezone, cfg.diary_reminder_enabled, cfg.morning_digest_enabled, cfg.log_level),
            reply_markup=_settings_keyboard(cfg.log_level),
        )
        return SETTINGS_MENU

    if data == "settings:toggle_diary":
        try:
            cfg = await service.toggle_diary_reminder()
        except SettingsPersistenceError as exc:
            await query.message.reply_text(f"⚠️ Не удалось сохранить настройки: {exc}")
            return SETTINGS_MENU
        await query.message.reply_text(
            _settings_text(cfg.timezone, cfg.diary_reminder_enabled, cfg.morning_digest_enabled, cfg.log_level),
            reply_markup=_settings_keyboard(cfg.log_level),
        )
        return SETTINGS_MENU

    if data == "settings:toggle_digest":
        try:
            cfg = await service.toggle_morning_digest()
        except SettingsPersistenceError as exc:
            await query.message.reply_text(f"⚠️ Не удалось сохранить настройки: {exc}")
            return SETTINGS_MENU
        await query.message.reply_text(
            _settings_text(cfg.timezone, cfg.diary_reminder_enabled, cfg.morning_digest_enabled, cfg.log_level),
            reply_markup=_settings_keyboard(cfg.log_level),
        )
        return SETTINGS_MENU

    if data == "settings:sync":
        obsidian = ObsidianService()
        ok, err = await obsidian.sync_bidirectional()
        await sync_db_with_vault()
        text = "✅ Sync выполнен. БД обновлена по vault." if ok else f"⚠️ Ошибка sync: {err}\nБД обновлена из доступных файлов."
        cfg = await service.get_runtime_settings()
        await query.message.reply_text(text, reply_markup=_settings_keyboard(cfg.log_level))
        return SETTINGS_MENU

    if data == "settings:reload":
        script_path = os.path.expanduser("~/apps/obsidian-bot/scripts/update.sh")
        process = await asyncio.create_subprocess_exec(
            "/bin/zsh",
            "-lc",
            f"'{script_path}'",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            await query.message.reply_text("✅ Скрипт обновления запущен и завершился успешно.")
        else:
            error_text = stderr.decode("utf-8", errors="ignore").strip() or stdout.decode("utf-8", errors="ignore").strip()
            await query.message.reply_text(f"⚠️ Ошибка перезагрузки: {error_text[:1200]}")
        cfg = await service.get_runtime_settings()
        await query.message.reply_text(
            _settings_text(cfg.timezone, cfg.diary_reminder_enabled, cfg.morning_digest_enabled, cfg.log_level),
            reply_markup=_settings_keyboard(cfg.log_level),
        )
        return SETTINGS_MENU

    if data == "settings:back_to_settings":
        cfg = await service.get_runtime_settings()
        await query.message.reply_text(
            _settings_text(cfg.timezone, cfg.diary_reminder_enabled, cfg.morning_digest_enabled, cfg.log_level),
            reply_markup=_settings_keyboard(cfg.log_level),
        )
        return SETTINGS_MENU

    if data == "settings:back":
        await query.message.reply_text("Главное меню:", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    return SETTINGS_MENU


@owner_only
async def settings_timezone_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет новую timezone."""
    if not update.effective_message or not update.effective_message.text:
        return SETTINGS_TZ_INPUT
    timezone_name = update.effective_message.text.strip()
    service = SettingsService(SessionLocal)
    try:
        cfg = await service.set_timezone(timezone_name)
    except SettingsPersistenceError as exc:
        await update.effective_message.reply_text(f"⚠️ Не удалось сохранить настройки: {exc}")
        return SETTINGS_MENU
    except Exception:
        logger.error("Ошибка сохранения timezone в настройках", exc_info=True)
        await update.effective_message.reply_text("Некорректная timezone. Пример: Europe/Kaliningrad")
        return SETTINGS_TZ_INPUT

    await update.effective_message.reply_text(
        _settings_text(cfg.timezone, cfg.diary_reminder_enabled, cfg.morning_digest_enabled, cfg.log_level),
        reply_markup=_settings_keyboard(cfg.log_level),
    )
    return SETTINGS_MENU


@owner_only
async def settings_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена диалога настроек."""
    if update.effective_message:
        await update.effective_message.reply_text("Операция отменена.", reply_markup=get_main_menu_keyboard())
    return ConversationHandler.END


def register_settings_handlers(application: Application) -> None:
    """Регистрирует ConversationHandler раздела настроек."""
    conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r".*Настройки$"), settings_entry),
            CommandHandler("settings", settings_entry),
        ],
        states={
            SETTINGS_MENU: [CallbackQueryHandler(settings_menu_callback, pattern=r"^settings:")],
            SETTINGS_TZ_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_timezone_input)],
        },
        fallbacks=[CommandHandler("cancel", settings_cancel)],
        per_chat=True,
        per_user=True,
    )
    application.add_handler(conversation)
