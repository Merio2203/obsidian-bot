"""Сервис работы с runtime-настройками приложения."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import settings
from bot.database.crud import get_app_setting, upsert_app_setting

logger = logging.getLogger(__name__)

SETTINGS_TZ_KEY = "timezone"
SETTINGS_DIARY_REMINDER_KEY = "diary_reminder_enabled"
SETTINGS_MORNING_DIGEST_KEY = "morning_digest_enabled"
SETTINGS_LOG_LEVEL_KEY = "log_level"


@dataclass(frozen=True)
class RuntimeSettings:
    timezone: str
    diary_reminder_enabled: bool
    morning_digest_enabled: bool
    log_level: str


class SettingsPersistenceError(RuntimeError):
    """Ошибка сохранения настроек в БД."""


def _to_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "да"}


class SettingsService:
    """CRUD-обертка для настроек бота, сохраняемых в БД."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_runtime_settings(self) -> RuntimeSettings:
        async with self._session_factory() as session:
            tz_raw = await get_app_setting(session, SETTINGS_TZ_KEY)
            diary_raw = await get_app_setting(session, SETTINGS_DIARY_REMINDER_KEY)
            digest_raw = await get_app_setting(session, SETTINGS_MORNING_DIGEST_KEY)

        return RuntimeSettings(
            timezone=(tz_raw.value if tz_raw else settings.timezone),
            diary_reminder_enabled=_to_bool(diary_raw.value if diary_raw else None, True),
            morning_digest_enabled=_to_bool(digest_raw.value if digest_raw else None, True),
            log_level=(await self.get_log_level()),
        )

    async def set_timezone(self, timezone_name: str) -> RuntimeSettings:
        ZoneInfo(timezone_name)  # валидация timezone
        await self._persist_value(SETTINGS_TZ_KEY, timezone_name)
        return await self.get_runtime_settings()

    async def toggle_diary_reminder(self) -> RuntimeSettings:
        current = await self.get_runtime_settings()
        new_value = "true" if not current.diary_reminder_enabled else "false"
        await self._persist_value(SETTINGS_DIARY_REMINDER_KEY, new_value)
        return await self.get_runtime_settings()

    async def toggle_morning_digest(self) -> RuntimeSettings:
        current = await self.get_runtime_settings()
        new_value = "true" if not current.morning_digest_enabled else "false"
        await self._persist_value(SETTINGS_MORNING_DIGEST_KEY, new_value)
        return await self.get_runtime_settings()

    async def get_log_level(self) -> str:
        """Возвращает сохранённый уровень логирования."""
        async with self._session_factory() as session:
            level = await get_app_setting(session, SETTINGS_LOG_LEVEL_KEY)
        return (level.value if level else "INFO").upper()

    async def set_log_level(self, level_name: str) -> str:
        """Сохраняет уровень логирования."""
        normalized = level_name.upper()
        await self._persist_value(SETTINGS_LOG_LEVEL_KEY, normalized)
        return normalized

    async def _persist_value(self, key: str, value: str) -> None:
        """Сохраняет настройку с авто-восстановлением прав sqlite при readonly."""
        try:
            async with self._session_factory() as session:
                await upsert_app_setting(session, key, value)
            return
        except OperationalError as exc:
            if not _is_sqlite_readonly_error(exc):
                raise
            logger.error("SQLite readonly при сохранении настройки %s, пробуем восстановить права.", key, exc_info=True)
            await asyncio.to_thread(_ensure_sqlite_writable)
            try:
                async with self._session_factory() as session:
                    await upsert_app_setting(session, key, value)
                return
            except OperationalError as retry_exc:
                if _is_sqlite_readonly_error(retry_exc):
                    raise SettingsPersistenceError("База данных доступна только для чтения.") from retry_exc
                raise


def _is_sqlite_readonly_error(exc: OperationalError) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return "readonly" in message and "database" in message


def _extract_sqlite_path(database_url: str) -> Path | None:
    raw = database_url.strip()
    if raw.startswith("sqlite+aiosqlite:///"):
        raw = raw.replace("sqlite+aiosqlite:///", "sqlite:///", 1)
    if not raw.startswith("sqlite:///"):
        return None
    parsed = urlparse(raw)
    path = unquote(parsed.path)
    return Path(path)


def _ensure_sqlite_writable() -> None:
    db_path = _extract_sqlite_path(settings.database_url)
    if db_path is None:
        return
    db_dir = db_path.parent
    db_dir.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        db_path.touch(exist_ok=True)
    try:
        os.chmod(db_dir, 0o775)
    except Exception:
        logger.debug("Не удалось изменить права директории БД: %s", db_dir, exc_info=True)
    for candidate in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm"), Path(f"{db_path}-journal")):
        if not candidate.exists():
            continue
        try:
            os.chmod(candidate, 0o664)
        except Exception:
            logger.debug("Не удалось изменить права файла БД: %s", candidate, exc_info=True)
