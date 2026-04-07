"""Централизованная настройка логирования бота."""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path

LOG_DIR = Path("/app/data/logs")
LOG_RETENTION_DAYS = 30
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DEFAULT_LOG_LEVEL = "INFO"
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


def get_log_file_path() -> Path:
    """Возвращает путь к дневному лог-файлу: /app/data/logs/bot_YYYY-MM-DD.log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    return LOG_DIR / f"bot_{today}.log"


class TelegramErrorHandler(logging.Handler):
    """Отправляет ошибки уровня ERROR+ владельцу в Telegram."""

    def __init__(self, bot=None, owner_id: int | None = None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(level=logging.ERROR)
        self.bot = bot
        self.owner_id = owner_id

    async def _send_async(self, text: str) -> None:
        if not self.bot or not self.owner_id:
            return
        try:
            await self.bot.send_message(chat_id=self.owner_id, text=text)
        except Exception:
            pass

    def emit(self, record: logging.LogRecord) -> None:
        if not self.bot or not self.owner_id:
            return
        try:
            asctime = self.formatter.formatTime(record) if self.formatter else ""
            message = record.getMessage()
            text = (
                "🚨 Критическая ошибка бота\n\n"
                f"Модуль: {record.name}\n"
                f"Ошибка: {message}\n"
                f"Время: {asctime}"
            )
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._send_async(text))
            except RuntimeError:
                asyncio.run(self._send_async(text))
        except Exception:
            pass


def apply_log_level(level_name: str) -> str:
    """Применяет уровень логирования ко всем обработчикам основного логгера."""
    normalized = (level_name or DEFAULT_LOG_LEVEL).upper()
    level = LOG_LEVELS.get(normalized, logging.INFO)
    logger = logging.getLogger("obsidian_bot")
    logger.setLevel(level)
    for handler in logger.handlers:
        handler.setLevel(level if isinstance(handler, logging.handlers.TimedRotatingFileHandler) else logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    for handler in root.handlers:
        handler.setLevel(level if isinstance(handler, logging.handlers.TimedRotatingFileHandler) else logging.INFO)
    return normalized if normalized in LOG_LEVELS else DEFAULT_LOG_LEVEL


def setup_logger(
    bot=None,
    owner_id: int | None = None,
    level_name: str = DEFAULT_LOG_LEVEL,
) -> logging.Logger:  # type: ignore[no-untyped-def]
    """
    Настраивает логгер:
    - TimedRotatingFileHandler: ротация каждый день, хранение 30 дней
    - StreamHandler: вывод в консоль (для docker logs)
    - TelegramErrorHandler: отправка критических ошибок в Telegram
    """
    logger = logging.getLogger("obsidian_bot")
    logger.propagate = False

    formatter = logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    log_file = get_log_file_path()

    logger.handlers = [h for h in logger.handlers if not isinstance(h, TelegramErrorHandler)]
    if not any(
        isinstance(h, logging.handlers.TimedRotatingFileHandler)
        and Path(getattr(h, "baseFilename", "")) == log_file
        for h in logger.handlers
    ):
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=str(log_file),
            when="midnight",
            backupCount=LOG_RETENTION_DAYS,
            encoding="utf-8",
        )
        file_handler.suffix = "%Y-%m-%d"
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.handlers.TimedRotatingFileHandler) for h in logger.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    telegram_handler = TelegramErrorHandler(bot=bot, owner_id=owner_id)
    telegram_handler.setFormatter(formatter)
    logger.addHandler(telegram_handler)

    applied_level = apply_log_level(level_name)
    root = logging.getLogger()
    root.handlers = list(logger.handlers)
    root.setLevel(logger.level)
    logger.info("Логгер инициализирован. Текущий уровень: %s", applied_level)
    return logger
