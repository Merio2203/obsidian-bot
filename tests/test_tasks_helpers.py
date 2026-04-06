from __future__ import annotations

from datetime import date

import pytest

from bot.handlers.tasks import _parse_deadline, _parse_estimate, _split_ai_plan
from bot.utils.formatters import render_task_markdown


def test_parse_deadline_valid() -> None:
    assert _parse_deadline("06.04.2026") == date(2026, 4, 6)
    assert _parse_deadline("-") is None


def test_parse_deadline_invalid() -> None:
    with pytest.raises(ValueError):
        _parse_deadline("2026-04-06")


def test_parse_estimate() -> None:
    assert _parse_estimate("2") == 2.0
    assert _parse_estimate("1,5") == 1.5
    assert _parse_estimate("-") is None

    with pytest.raises(ValueError):
        _parse_estimate("-1")


def test_split_ai_plan() -> None:
    ai_text = (
        "## 🎯 Критерии готовности\n"
        "- [ ] Критерий 1\n"
        "- [ ] Критерий 2\n\n"
        "## 📝 Подзадачи\n"
        "- [ ] Подзадача 1\n"
        "- [ ] Подзадача 2\n"
    )
    criteria, subtasks = _split_ai_plan(ai_text)
    assert criteria == ["Критерий 1", "Критерий 2"]
    assert subtasks == ["Подзадача 1", "Подзадача 2"]


def test_render_task_markdown() -> None:
    markdown = render_task_markdown(
        title="Сделать API",
        project_name="CRM",
        priority="🔥 Высокий",
        description="Нужно реализовать эндпоинт",
        deadline_iso="2026-04-10",
        estimated_time=3.5,
        created_at="2026-04-06 10:00",
        criteria_items=["Тесты проходят"],
        subtask_items=["Подготовить схему"],
    )
    assert "title: Сделать API" in markdown
    assert "project: CRM" in markdown
    assert "- [ ] Тесты проходят" in markdown
    assert "- [ ] Подготовить схему" in markdown
