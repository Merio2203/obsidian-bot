from __future__ import annotations

from bot.utils.formatters import render_diary_append_block, render_diary_markdown


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
    assert "mood: 😊" in markdown
    assert "## 🌅 Как прошёл день" in markdown
    assert "## 🎯 Планы на завтра" in markdown


def test_render_diary_append_block() -> None:
    block = render_diary_append_block(
        mood="😐",
        day_text="Насыщенный день",
        done_text="- Код-ревью",
        ideas_text="Подумать про кэш",
        tomorrow_text="- Написать тесты",
    )
    assert "## ➕ Дополнение" in block
    assert "Настроение: 😐" in block
    assert "### ✅ Что сделал" in block
