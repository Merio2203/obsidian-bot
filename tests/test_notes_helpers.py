from __future__ import annotations

from bot.handlers.notes import _extract_title, _normalize_tags
from bot.utils.formatters import render_note_markdown


def test_extract_title() -> None:
    assert _extract_title("Первая строка\nвторая строка") == "Первая строка"
    assert _extract_title("   ") == "Новая заметка"


def test_normalize_tags() -> None:
    tags = _normalize_tags("#Python, продуктивность, python,  ai tools ")
    assert tags == ["python", "продуктивность", "ai-tools"]


def test_render_note_markdown() -> None:
    markdown = render_note_markdown(
        title="Идея по интеграции",
        note_type="idea",
        tags=["idea", "telegram"],
        content="Сделать быстрый импорт заметок",
    )
    assert "title: Идея по интеграции" in markdown
    assert "type: idea" in markdown
    assert "tags: [idea, telegram]" in markdown
