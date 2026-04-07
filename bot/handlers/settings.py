"""Хендлеры раздела настроек."""

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
from bot.services.obsidian_service import ObsidianService
from bot.services.settings_service import SettingsService
from bot.utils.decorators import owner_only
from bot.utils.keyboards import get_main_menu_keyboard

logger = logging.getLogger(__name__)

SETTINGS_MENU, SETTINGS_TZ_INPUT = range(2)


def _settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🌍 Изменить timezone", callback_data="settings:set_tz")],
            [InlineKeyboardButton("📓 Переключить напоминание дневника", callback_data="settings:toggle_diary")],
            [InlineKeyboardButton("🌅 Переключить утренний дайджест", callback_data="settings:toggle_digest")],
            [InlineKeyboardButton("🔄 Синхронизировать сейчас", callback_data="settings:sync")],
            [InlineKeyboardButton("◀️ Назад", callback_data="settings:back")],
        ]
    )


def _settings_text(timezone_name: str, diary_enabled: bool, digest_enabled: bool) -> str:
    diary_state = "ВКЛ" if diary_enabled else "ВЫКЛ"
    digest_state = "ВКЛ" if digest_enabled else "ВЫКЛ"
    return (
        "⚙️ Текущие настройки:\n\n"
        f"- Timezone: {timezone_name}\n"
        f"- Напоминание о дневнике: {diary_state}\n"
        f"- Утренний дайджест: {digest_state}"
    )


@owner_only
async def settings_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа в настройки."""
    if not update.effective_message:
        return ConversationHandler.END
    service = SettingsService(SessionLocal)
    cfg = await service.get_runtime_settings()
    await update.effective_message.reply_text(
        _settings_text(cfg.timezone, cfg.diary_reminder_enabled, cfg.morning_digest_enabled),
        reply_markup=_settings_keyboard(),
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

    if data == "settings:toggle_diary":
        cfg = await service.toggle_diary_reminder()
        await query.message.reply_text(
            _settings_text(cfg.timezone, cfg.diary_reminder_enabled, cfg.morning_digest_enabled),
            reply_markup=_settings_keyboard(),
        )
        return SETTINGS_MENU

    if data == "settings:toggle_digest":
        cfg = await service.toggle_morning_digest()
        await query.message.reply_text(
            _settings_text(cfg.timezone, cfg.diary_reminder_enabled, cfg.morning_digest_enabled),
            reply_markup=_settings_keyboard(),
        )
        return SETTINGS_MENU

    if data == "settings:sync":
        obsidian = ObsidianService()
        ok, err = await obsidian.sync_to_dropbox()
        text = "✅ Sync выполнен." if ok else f"⚠️ Ошибка sync: {err}"
        await query.message.reply_text(text, reply_markup=_settings_keyboard())
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
    except Exception:
        logger.error("Ошибка сохранения timezone в настройках", exc_info=True)
        await update.effective_message.reply_text("Некорректная timezone. Пример: Europe/Kaliningrad")
        return SETTINGS_TZ_INPUT

    await update.effective_message.reply_text(
        _settings_text(cfg.timezone, cfg.diary_reminder_enabled, cfg.morning_digest_enabled),
        reply_markup=_settings_keyboard(),
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
