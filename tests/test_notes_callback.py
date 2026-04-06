from __future__ import annotations

import types

import pytest

from bot.handlers.notes import notes_action_callback


class FakeMessage:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.sent.append(text)


class FakeCallbackQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = FakeMessage()
        self.answered = False

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answered = True


class FakeUpdate:
    def __init__(self, user_id: int, data: str) -> None:
        self.effective_user = types.SimpleNamespace(id=user_id)
        self.callback_query = FakeCallbackQuery(data=data)
        self.effective_message = None


@pytest.mark.asyncio
async def test_notes_menu_callback() -> None:
    update = FakeUpdate(user_id=42, data="notes:menu")
    context = types.SimpleNamespace(user_data={})
    await notes_action_callback(update, context)

    assert update.callback_query.answered is True
    assert update.callback_query.message.sent
    assert "Главное меню" in update.callback_query.message.sent[0]
