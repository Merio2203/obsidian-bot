"""Точка входа Telegram-бота."""

from __future__ import annotations

import asyncio
import logging
import signal

from telegram.ext import Application, ContextTypes

from bot.config import settings
from bot.database import SessionLocal, engine
from bot.database.models import init_db
from bot.handlers.menu import register_menu_handlers
from bot.services.ai_service import AIService
from bot.services.obsidian_service import ObsidianService, sync_db_with_vault
from bot.services.scheduler_service import BotSchedulerService
from bot.services.settings_service import SettingsService
from bot.utils.logger import apply_log_level, setup_logger
from bot.utils.keyboards import get_mini_app_keyboard

logger = logging.getLogger(__name__)


async def on_startup() -> None:
    """Инициализация инфраструктуры при старте."""
    await init_db(engine)
    obsidian = ObsidianService()
    await obsidian.ensure_dirs()
    sync_ok, sync_error = await obsidian.sync_from_dropbox()
    if sync_ok:
        logger.info("Vault успешно синхронизирован из Dropbox при старте.")
    elif sync_error:
        logger.warning("Не удалось подтянуть изменения из Dropbox при старте: %s", sync_error)
    await sync_db_with_vault()
    runtime_settings = await SettingsService(SessionLocal).get_runtime_settings()
    apply_log_level(runtime_settings.log_level)
    _ = AIService(SessionLocal)


async def run_bot() -> None:
    """Запускает bot polling c graceful shutdown."""
    setup_logger(level_name="INFO")
    await on_startup()

    app = Application.builder().token(settings.telegram_bot_token).build()
    register_menu_handlers(app)
    app.add_error_handler(error_handler)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_stop() -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            # На некоторых платформах (например Windows) add_signal_handler недоступен.
            pass

    await app.initialize()
    runtime_settings = await SettingsService(SessionLocal).get_runtime_settings()
    setup_logger(
        bot=app.bot,
        owner_id=settings.telegram_owner_id,
        level_name=runtime_settings.log_level,
    )
    await app.start()
    scheduler_service = BotSchedulerService(app)
    await scheduler_service.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Бот запущен и ожидает сообщения.")

    await stop_event.wait()

    logger.info("Получен сигнал завершения, останавливаем бот.")
    await scheduler_service.shutdown()
    await app.updater.stop()
    await app.stop()
    await app.shutdown()


def main() -> None:
    """Синхронная оболочка для запуска асинхронного приложения."""
    asyncio.run(run_bot())


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Глобальный обработчик необработанных исключений."""
    logger.error("Необработанное исключение", exc_info=context.error)
    try:
        effective_message = getattr(update, "effective_message", None)
        if effective_message:
            await effective_message.reply_text(
                "⚠️ Произошла ошибка. Попробуйте ещё раз или нажмите /start",
                reply_markup=get_mini_app_keyboard(),
            )
    except Exception:
        logger.debug("Не удалось отправить сообщение об ошибке пользователю", exc_info=True)


if __name__ == "__main__":
    main()
