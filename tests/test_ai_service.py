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
        assert fake_create.calls[0]["max_tokens"] == 80

        await engine.dispose()


@pytest.mark.asyncio
async def test_ai_service_includes_wikilink_rules_in_prompt() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}")
        await init_db(engine)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        service = AIService(session_factory)

        fake_create = FakeCreate()
        service._client = SimpleNamespace(chat=SimpleNamespace(completions=fake_create))  # type: ignore[attr-defined]

        await service.generate_links_for_content(
            content_type="resource",
            text="Тест",
            existing_links=["Проект Сайт", "2026-03-27"],
        )

        system_prompt = fake_create.calls[0]["messages"][0]["content"]
        assert "НЕ используй markdown-ссылки" in system_prompt
        assert "НЕ добавляй расширение .md" in system_prompt
        assert "ТОЛЬКО имена из предоставленного списка" in system_prompt

        await engine.dispose()
