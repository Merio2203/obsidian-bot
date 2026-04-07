from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import bot.handlers.today as today_module
from bot.config import settings
from bot.database.crud import create_diary_entry, create_task, update_task_status
from bot.database.models import init_db


@pytest.mark.asyncio
async def test_today_dashboard_contains_sections() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}")
        await init_db(engine)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        today = datetime.now(ZoneInfo(settings.timezone)).date()

        async with session_factory() as session:
            t1 = await create_task(
                session=session,
                project_id=None,
                title="Сделать релиз",
                priority="🔥 Высокий",
                task_type="task",
                deadline=today,
                estimated_time=2.0,
                obsidian_path="Входящие/release.md",
            )
            t2 = await create_task(
                session=session,
                project_id=None,
                title="Старый долг",
                priority="⚡ Средний",
                task_type="task",
                deadline=today - timedelta(days=1),
                estimated_time=1.0,
                obsidian_path="Входящие/debt.md",
            )
            await update_task_status(session, t2, "🟡 В работе")
            await create_diary_entry(session, today, f"Дневник/{today.isoformat()}.md")

        old_factory = today_module.SessionLocal
        try:
            today_module.SessionLocal = session_factory  # type: ignore[assignment]
            text = await today_module.build_today_dashboard_text()
        finally:
            today_module.SessionLocal = old_factory  # type: ignore[assignment]

        assert "## 🗓️ Задачи на сегодня" in text
        assert "## 🔧 В работе" in text
        assert "## ⏰ Просроченные" in text
        assert "## 📅 Google Calendar" in text
        assert "## 📓 Дневник" in text
        assert "Сделать релиз" in text

        await engine.dispose()
