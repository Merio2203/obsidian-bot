from __future__ import annotations

import tempfile
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.crud import create_diary_entry, get_diary_entry_by_date
from bot.database.models import init_db


@pytest.mark.asyncio
async def test_create_and_get_diary_entry() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}")
        await init_db(engine)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            created = await create_diary_entry(
                session=session,
                entry_date=date(2026, 4, 6),
                obsidian_path="Дневник/2026-04-06.md",
            )
            assert created.id > 0

            loaded = await get_diary_entry_by_date(session, date(2026, 4, 6))
            assert loaded is not None
            assert loaded.obsidian_path == "Дневник/2026-04-06.md"

        await engine.dispose()
