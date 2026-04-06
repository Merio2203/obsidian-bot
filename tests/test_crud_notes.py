from __future__ import annotations

import tempfile

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.crud import create_note
from bot.database.models import Note, init_db


@pytest.mark.asyncio
async def test_create_note() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}")
        await init_db(engine)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            note = await create_note(
                session=session,
                title="Быстрая мысль",
                note_type="idea",
                content="Проверить автотеги",
                tags="idea,ai",
                obsidian_path="💡 Идеи/быстрая-мысль.md",
            )
            assert note.id > 0
            assert note.type == "idea"

            loaded = await session.get(Note, note.id)
            assert loaded is not None
            assert loaded.title == "Быстрая мысль"

        await engine.dispose()
