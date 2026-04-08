from __future__ import annotations

import tempfile
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.crud import create_task, get_task_by_id, get_tasks, update_task_completed
from bot.database.models import init_db


@pytest.mark.asyncio
async def test_create_and_update_task() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}")
        await init_db(engine)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            task = await create_task(
                session=session,
                project_id=None,
                title="Новая задача",
                priority="⚡ Средний",
                task_type="task",
                deadline=date(2026, 4, 7),
                estimated_time=2.0,
                obsidian_path="Входящие/new-task.md",
            )
            assert task.id > 0

            loaded = await get_task_by_id(session, task.id)
            assert loaded is not None
            assert loaded.title == "Новая задача"

            tasks = await get_tasks(session)
            assert tasks

            await update_task_completed(session, task, True)
            updated = await get_task_by_id(session, task.id)
            assert updated is not None
            assert updated.completed is True

        await engine.dispose()
