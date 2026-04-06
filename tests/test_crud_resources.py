from __future__ import annotations

import tempfile

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.crud import create_resource
from bot.database.models import Resource, init_db


@pytest.mark.asyncio
async def test_create_resource() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}")
        await init_db(engine)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            resource = await create_resource(
                session=session,
                title="Видео про архитектуру",
                url="https://youtu.be/test",
                resource_type="youtube",
                tags="architecture,backend",
                obsidian_path="📚 Ресурсы/Видео/video.md",
            )
            assert resource.id > 0
            assert resource.type == "youtube"
            loaded = await session.get(Resource, resource.id)
            assert loaded is not None
            assert loaded.url == "https://youtu.be/test"

        await engine.dispose()
