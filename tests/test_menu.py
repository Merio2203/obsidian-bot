from __future__ import annotations

import types

import pytest

from bot.handlers.menu import menu_router, start_handler


class FakeMessage:
    def __init__(self, text: str | None = None) -> None:
        self.text = text
        self.sent: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.sent.append(text)


class FakeUpdate:
    def __init__(self, user_id: int, text: str | None = None) -> None:
        self.effective_user = types.SimpleNamespace(id=user_id)
        self.effective_message = FakeMessage(text=text)
        self.callback_query = None


@pytest.mark.asyncio
async def test_start_handler_shows_greeting() -> None:
    update = FakeUpdate(user_id=42)
    await start_handler(update, None)
    assert update.effective_message.sent
    assert "Obsidian AI-ассистент" in update.effective_message.sent[0]


@pytest.mark.asyncio
async def test_menu_router_handles_button() -> None:
    update = FakeUpdate(user_id=42, text="📁 Проекты")
    await menu_router(update, None)
    assert update.effective_message.sent
    assert "Раздел проектов" in update.effective_message.sent[0]
