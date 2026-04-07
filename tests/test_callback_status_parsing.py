from __future__ import annotations

import types

import pytest

import bot.handlers.projects as projects_module
import bot.handlers.tasks as tasks_module


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
async def test_tasks_set_status_callback_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"value": False}

    async def fake_set_task_status(update, context, task_id: int, status: str) -> None:  # type: ignore[no-untyped-def]
        called["value"] = True
        assert task_id == 123
        assert status == "🔴 Новая"

    monkeypatch.setattr(tasks_module, "_set_task_status", fake_set_task_status)

    update = FakeUpdate(user_id=42, data="tasks:set_status:123:new")
    context = types.SimpleNamespace(user_data={})
    await tasks_module.tasks_menu_callback(update, context)

    assert called["value"] is True
    assert update.callback_query.answered is True


@pytest.mark.asyncio
async def test_projects_set_status_callback_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"value": False}

    async def fake_set_project_status(update, context, status: str) -> None:  # type: ignore[no-untyped-def]
        called["value"] = True
        assert status == "🟡 Активный"

    monkeypatch.setattr(projects_module, "_set_project_status", fake_set_project_status)

    update = FakeUpdate(user_id=42, data="projects:set_status:active")
    context = types.SimpleNamespace(user_data={"current_project_name": "Test"})
    await projects_module.projects_menu_callback(update, context)

    assert called["value"] is True
    assert update.callback_query.answered is True
