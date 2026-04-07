from __future__ import annotations

from datetime import date

import pytest

from bot.handlers.tasks import _normalize_links, _normalize_tags, _parse_deadline, _parse_estimate
from bot.utils.formatters import format_wikilinks_for_yaml, render_task_markdown


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


def test_normalize_tags_and_links() -> None:
    assert _normalize_tags(["#Python", "backend api", "python"]) == ["python", "backend-api"]
    assert _normalize_links(["Проект А", "[[Проект Б]]"]) == ["[[Проект А]]", "[[Проект Б]]"]
    assert _normalize_links(["Проект Сайт.md", "[Сайт](Проекты/Проект Сайт.md)"]) == [
        "[[Проект Сайт]]",
        "[[Проект Сайт|Сайт]]",
    ]


def test_render_task_markdown() -> None:
    markdown = render_task_markdown(
        title="Сделать API",
        project_name="CRM",
        priority="🔥 Высокий",
        description="Нужно реализовать эндпоинт",
        deadline_iso="2026-04-10",
        estimated_time=3.5,
        created_at="2026-04-06 10:00",
        tags=["backend", "api"],
        links=["[[CRM]]", "[[Сделать API]]"],
    )
    assert "title: Сделать API" in markdown
    assert "project: CRM" in markdown
    assert "tags: [backend, api]" in markdown
    assert '  - "[[CRM]]"' in markdown
    assert '  - "[[Сделать API]]"' in markdown


def test_format_wikilinks_for_yaml() -> None:
    block = format_wikilinks_for_yaml(["Проект Сайт.md", "[[2026-03-27|Дневник]]"])
    assert block.startswith("links:\n")
    assert '  - "[[Проект Сайт]]"' in block
    assert '  - "[[2026-03-27|Дневник]]"' in block
