"""Централизованная настройка логирования бота."""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
from pathlib import Path

LOG_FILE = Path("/app/data/bot.log")
LOG_RETENTION_DAYS = 30
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


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
            # Ошибки нотификаций не должны ломать основное логирование.
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


def setup_logger(bot=None, owner_id: int | None = None) -> logging.Logger:  # type: ignore[no-untyped-def]
    """
    Настраивает логгер:
    - TimedRotatingFileHandler: ротация каждый день, хранение 30 дней
    - StreamHandler: вывод в консоль (для docker logs)
    - TelegramErrorHandler: отправка критических ошибок в Telegram
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    formatter = logging.Formatter(LOG_FORMAT)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Чтобы не плодить дубли хендлеров при повторных вызовах.
    has_rotating = any(isinstance(h, logging.handlers.TimedRotatingFileHandler) for h in root.handlers)
    has_stream = any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.handlers.TimedRotatingFileHandler) for h in root.handlers)

    if not has_rotating:
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=str(LOG_FILE),
            when="midnight",
            backupCount=LOG_RETENTION_DAYS,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    if not has_stream:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    # Удаляем старые TelegramErrorHandler, чтобы обновить bot/owner_id.
    root.handlers = [h for h in root.handlers if not isinstance(h, TelegramErrorHandler)]
    telegram_handler = TelegramErrorHandler(bot=bot, owner_id=owner_id)
    telegram_handler.setFormatter(formatter)
    root.addHandler(telegram_handler)

    return root
