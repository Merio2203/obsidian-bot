"""Сервис работы с runtime-настройками приложения."""

from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import settings
from bot.database.crud import get_app_setting, upsert_app_setting


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
        async with self._session_factory() as session:
            await upsert_app_setting(session, SETTINGS_TZ_KEY, timezone_name)
        return await self.get_runtime_settings()

    async def toggle_diary_reminder(self) -> RuntimeSettings:
        current = await self.get_runtime_settings()
        new_value = "true" if not current.diary_reminder_enabled else "false"
        async with self._session_factory() as session:
            await upsert_app_setting(session, SETTINGS_DIARY_REMINDER_KEY, new_value)
        return await self.get_runtime_settings()

    async def toggle_morning_digest(self) -> RuntimeSettings:
        current = await self.get_runtime_settings()
        new_value = "true" if not current.morning_digest_enabled else "false"
        async with self._session_factory() as session:
            await upsert_app_setting(session, SETTINGS_MORNING_DIGEST_KEY, new_value)
        return await self.get_runtime_settings()

    async def get_log_level(self) -> str:
        """Возвращает сохранённый уровень логирования."""
        async with self._session_factory() as session:
            level = await get_app_setting(session, SETTINGS_LOG_LEVEL_KEY)
        return (level.value if level else "INFO").upper()

    async def set_log_level(self, level_name: str) -> str:
        """Сохраняет уровень логирования."""
        normalized = level_name.upper()
        async with self._session_factory() as session:
            await upsert_app_setting(session, SETTINGS_LOG_LEVEL_KEY, normalized)
        return normalized
