from __future__ import annotations

import tempfile

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.models import init_db
from bot.services.settings_service import SettingsService


@pytest.mark.asyncio
async def test_settings_service_toggle_and_timezone() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}")
        await init_db(engine)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        service = SettingsService(session_factory)

        cfg = await service.get_runtime_settings()
        assert cfg.diary_reminder_enabled is True
        assert cfg.morning_digest_enabled is True

        cfg = await service.toggle_diary_reminder()
        assert cfg.diary_reminder_enabled is False

        cfg = await service.toggle_morning_digest()
        assert cfg.morning_digest_enabled is False

        cfg = await service.set_timezone("Europe/Kaliningrad")
        assert cfg.timezone == "Europe/Kaliningrad"

        await engine.dispose()
