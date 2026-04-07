from __future__ import annotations

from bot.utils.formatters import render_diary_markdown


def test_render_diary_markdown() -> None:
    markdown = render_diary_markdown(
        date_iso="2026-04-06",
        mood="😊",
        day_text="День прошел отлично",
        done_text="- Закрыл задачу",
        ideas_text="Идея новой функции",
        tomorrow_text="- Подготовить релиз",
    )
    assert "date: 2026-04-06" in markdown
    assert "title: Дневник за 06.04.2026" in markdown
    assert "mood: 😊" in markdown
    assert "# Дневник за 06.04.2026" in markdown
    assert "## 🌅 Как прошёл день" in markdown
    assert "## 🎯 Планы на завтра" in markdown
