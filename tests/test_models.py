from __future__ import annotations

import tempfile
from datetime import date

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.models import AICache, Base, DiaryEntry, init_db


@pytest.mark.asyncio
async def test_init_db_creates_tables() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}")
        await init_db(engine)

        async with engine.begin() as conn:
            tables = await conn.run_sync(lambda c: inspect(c).get_table_names())

        assert "projects" in tables
        assert "tasks" in tables
        assert "notes" in tables
        assert "app_settings" in tables
        assert "ai_cache" in tables
        await engine.dispose()


@pytest.mark.asyncio
async def test_unique_constraints() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}")
        await init_db(engine)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            session.add(AICache(prompt_hash="hash-1", task_type="tags", response="ok"))
            await session.commit()

            session.add(AICache(prompt_hash="hash-1", task_type="tags", response="dup"))
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()

            session.add(DiaryEntry(date=date(2026, 1, 1), obsidian_path="a.md"))
            await session.commit()
            session.add(DiaryEntry(date=date(2026, 1, 1), obsidian_path="b.md"))
            with pytest.raises(IntegrityError):
                await session.commit()

        await engine.dispose()
