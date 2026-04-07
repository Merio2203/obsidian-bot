"""Тесты логгера и уровней обработчиков."""

from __future__ import annotations

import logging

from bot.utils import logger as logger_module


def test_telegram_handler_stays_error_level(tmp_path) -> None:
    """Проверяет, что Telegram-обработчик не понижается до INFO/DEBUG."""
    app_logger = logging.getLogger("obsidian_bot")
    root_logger = logging.getLogger()
    old_app_handlers = list(app_logger.handlers)
    old_root_handlers = list(root_logger.handlers)
    old_app_level = app_logger.level
    old_root_level = root_logger.level

    logger_module.LOG_DIR = tmp_path  # type: ignore[assignment]

    try:
        logger = logger_module.setup_logger(bot=object(), owner_id=1, level_name="INFO")
        tg_handlers = [h for h in logger.handlers if isinstance(h, logger_module.TelegramErrorHandler)]
        assert len(tg_handlers) == 1

        # При первоначальной настройке и после смены уровня Telegram-handler остаётся ERROR.
        assert tg_handlers[0].level == logging.ERROR
        logger_module.apply_log_level("DEBUG")
        assert tg_handlers[0].level == logging.ERROR

        # Telegram-handler не должен устанавливаться в root, иначе он ловит все сторонние логи.
        assert not any(isinstance(h, logger_module.TelegramErrorHandler) for h in logging.getLogger().handlers)
    finally:
        new_handlers = [h for h in app_logger.handlers if h not in old_app_handlers]
        for handler in new_handlers:
            handler.close()
        app_logger.handlers = old_app_handlers
        app_logger.setLevel(old_app_level)
        root_logger.handlers = old_root_handlers
        root_logger.setLevel(old_root_level)
