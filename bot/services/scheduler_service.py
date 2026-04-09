"""Сервис фоновых задач: напоминания, дайджест и backup БД."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from bot.config import settings
from bot.database import SessionLocal
from bot.database.crud import get_diary_entry_by_date, get_setting, set_setting
from bot.handlers.today import build_today_dashboard_text
from bot.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

CHECK_INTERVAL_MINUTES = 5
DIARY_REMINDER_HOUR = 21
MORNING_DIGEST_HOUR = 9
DB_BACKUP_HOUR = 3

SETTING_LAST_DIARY_REMINDER = "scheduler_last_diary_reminder_date"
SETTING_LAST_MORNING_DIGEST = "scheduler_last_morning_digest_date"
SETTING_LAST_DB_BACKUP = "scheduler_last_db_backup_date"


class BotSchedulerService:
    """Планировщик периодических задач для владельца бота."""

    def __init__(self, app: Application) -> None:
        self._app = app
        self._scheduler = AsyncIOScheduler()
        self._started = False

    async def start(self) -> None:
        """Запускает планировщик фоновых задач."""
        if self._started:
            return
        self._scheduler.add_job(
            self._tick,
            trigger="interval",
            minutes=CHECK_INTERVAL_MINUTES,
            id="scheduler_tick",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.start()
        self._started = True
        logger.info("Планировщик задач запущен.")

    async def shutdown(self) -> None:
        """Останавливает планировщик."""
        if not self._started:
            return
        self._scheduler.shutdown(wait=False)
        self._started = False
        logger.info("Планировщик задач остановлен.")

    async def _tick(self) -> None:
        """Периодическая проверка окон запуска задач по локальному timezone."""
        runtime = await SettingsService(SessionLocal).get_runtime_settings()
        tz = ZoneInfo(runtime.timezone)
        now = datetime.now(tz)
        today_iso = now.date().isoformat()

        if runtime.diary_reminder_enabled and now.hour == DIARY_REMINDER_HOUR:
            await self._run_once_per_day(
                setting_key=SETTING_LAST_DIARY_REMINDER,
                today_iso=today_iso,
                coro=self._send_diary_reminder,
            )

        if runtime.morning_digest_enabled and now.hour == MORNING_DIGEST_HOUR:
            await self._run_once_per_day(
                setting_key=SETTING_LAST_MORNING_DIGEST,
                today_iso=today_iso,
                coro=self._send_morning_digest,
            )

        if now.hour == DB_BACKUP_HOUR:
            await self._run_once_per_day(
                setting_key=SETTING_LAST_DB_BACKUP,
                today_iso=today_iso,
                coro=self._backup_db_to_dropbox,
            )

    async def _run_once_per_day(self, setting_key: str, today_iso: str, coro) -> None:  # type: ignore[no-untyped-def]
        async with SessionLocal() as session:
            already_run = await get_setting(session, setting_key)
            if already_run == today_iso:
                return
        ok = await coro()
        if not ok:
            return
        async with SessionLocal() as session:
            await set_setting(session, setting_key, today_iso)

    async def _send_diary_reminder(self) -> bool:
        runtime = await SettingsService(SessionLocal).get_runtime_settings()
        tz = ZoneInfo(runtime.timezone)
        today = datetime.now(tz).date()
        async with SessionLocal() as session:
            entry = await get_diary_entry_by_date(session, today)
        if entry is not None:
            return True
        await self._safe_send_message(
            "📓 Напоминание: дневник за сегодня ещё не заполнен. "
            "Открой раздел «Дневник» и зафиксируй день."
        )
        return True

    async def _send_morning_digest(self) -> bool:
        text = await build_today_dashboard_text()
        await self._safe_send_message(f"🌅 Утренний дайджест:\n\n{text}")
        return True

    async def _backup_db_to_dropbox(self) -> bool:
        db_path = self._extract_sqlite_path(settings.database_url)
        if db_path is None:
            logger.warning("DB backup пропущен: DATABASE_URL не sqlite.")
            return False
        if not await asyncio.to_thread(db_path.exists):
            logger.warning("DB backup пропущен: файл БД не найден (%s).", db_path)
            return False

        timestamp = datetime.utcnow().strftime("%Y-%m-%d")
        target = f"dropbox:{settings.dropbox_db_backup_path.rstrip('/')}/bot_{timestamp}.db"
        process = await asyncio.create_subprocess_exec(
            "rclone",
            "copyto",
            str(db_path),
            target,
            "--quiet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            error_text = stderr.decode("utf-8", errors="ignore").strip() or "unknown error"
            logger.error("Ошибка backup БД в Dropbox: %s", error_text)
            await self._safe_send_message(f"⚠️ Backup БД не выполнен: {error_text}")
            return False
        await self._safe_send_message(f"🗄️ Backup БД в Dropbox выполнен: bot_{timestamp}.db")
        return True

    async def _safe_send_message(self, text: str) -> None:
        try:
            await self._app.bot.send_message(chat_id=settings.telegram_owner_id, text=text)
        except Exception:  # noqa: BLE001
            logger.error("Не удалось отправить сообщение владельцу из scheduler", exc_info=True)

    @staticmethod
    def _extract_sqlite_path(database_url: str) -> Path | None:
        raw = database_url.strip()
        if raw.startswith("sqlite+aiosqlite:///"):
            raw = raw.replace("sqlite+aiosqlite:///", "sqlite:///", 1)
        if not raw.startswith("sqlite:///"):
            return None
        parsed = urlparse(raw)
        path = unquote(parsed.path)
        return Path(path)
