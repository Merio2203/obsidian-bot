from __future__ import annotations

import tempfile
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.models import init_db
from bot.services.ai_service import AIService


class FakeCreate:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="готово"))]
        )


@pytest.mark.asyncio
async def test_ai_service_uses_max_tokens_and_cache() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}")
        await init_db(engine)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        service = AIService(session_factory)

        fake_create = FakeCreate()
        service._client = SimpleNamespace(chat=SimpleNamespace(completions=fake_create))  # type: ignore[attr-defined]

        first = await service.generate_tags("Новая идея по проекту")
        second = await service.generate_tags("Новая идея по проекту")

        assert first == "готово"
        assert second == "готово"
        assert len(fake_create.calls) == 1
        assert fake_create.calls[0]["max_tokens"] == 50

        await engine.dispose()
