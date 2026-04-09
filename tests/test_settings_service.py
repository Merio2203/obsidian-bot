from __future__ import annotations

import tempfile

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import bot.services.settings_service as settings_service_module
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


@pytest.mark.asyncio
async def test_settings_service_retries_on_readonly(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}")
        await init_db(engine)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        service = SettingsService(session_factory)

        calls = {"count": 0, "recovered": False}

        async def fake_upsert(session, key: str, value: str):  # type: ignore[no-untyped-def]
            calls["count"] += 1
            if calls["count"] == 1:
                raise OperationalError(
                    "UPDATE app_settings ...",
                    {},
                    Exception("attempt to write a readonly database"),
                )
            return None

        def fake_recover() -> None:
            calls["recovered"] = True

        monkeypatch.setattr(settings_service_module, "upsert_app_setting", fake_upsert)
        monkeypatch.setattr(settings_service_module, "_ensure_sqlite_writable", fake_recover)

        level = await service.set_log_level("warning")
        assert level == "WARNING"
        assert calls["recovered"] is True
        assert calls["count"] == 2

        await engine.dispose()
