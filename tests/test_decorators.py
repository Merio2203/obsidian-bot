from __future__ import annotations

import types

import pytest

from bot.utils.decorators import owner_only


class FakeMessage:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.sent.append(text)


class FakeCallbackQuery:
    def __init__(self, message: FakeMessage) -> None:
        self.message = message
        self.answered = False

    async def answer(self, text: str, show_alert: bool = False) -> None:
        self.answered = True


class FakeUpdate:
    def __init__(self, user_id: int, with_callback: bool = False) -> None:
        self.effective_user = types.SimpleNamespace(id=user_id)
        self.effective_message = FakeMessage()
        self.callback_query = FakeCallbackQuery(self.effective_message) if with_callback else None


@pytest.mark.asyncio
async def test_owner_only_allows_owner() -> None:
    called = {"value": False}

    @owner_only
    async def sample(update, context):  # type: ignore[no-untyped-def]
        called["value"] = True

    update = FakeUpdate(user_id=42)
    await sample(update, None)
    assert called["value"] is True


@pytest.mark.asyncio
async def test_owner_only_blocks_other_user_message() -> None:
    called = {"value": False}

    @owner_only
    async def sample(update, context):  # type: ignore[no-untyped-def]
        called["value"] = True

    update = FakeUpdate(user_id=999)
    await sample(update, None)

    assert called["value"] is False
    assert update.effective_message.sent


@pytest.mark.asyncio
async def test_owner_only_blocks_other_user_callback() -> None:
    @owner_only
    async def sample(update, context):  # type: ignore[no-untyped-def]
        return None

    update = FakeUpdate(user_id=999, with_callback=True)
    await sample(update, None)
    assert update.callback_query is not None
    assert update.callback_query.answered is True
