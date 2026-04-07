from __future__ import annotations

from bot.handlers.diary import _extract_section_content, _replace_section_content


def _sample() -> str:
    return (
        "---\n"
        "title: Дневник за 07.04.2026\n"
        "date: 2026-04-07\n"
        "mood: 😊\n"
        "tags: [дневник]\n"
        "---\n\n"
        "# Дневник за 07.04.2026\n\n"
        "## 🌅 Как прошёл день\n"
        "Старый текст дня\n\n"
        "## ✅ Что сделал\n"
        "Старый done\n\n"
        "## 💭 Мысли и идеи\n"
        "Старые идеи\n\n"
        "## 🎯 Планы на завтра\n"
        "Старые планы\n"
    )


def test_extract_section_content() -> None:
    content = _sample()
    current = _extract_section_content(content, "✅ Что сделал")
    assert current == "Старый done"


def test_replace_section_content() -> None:
    content = _sample()
    updated = _replace_section_content(content, "💭 Мысли и идеи", "Новый текст")
    assert "## 💭 Мысли и идеи\nНовый текст\n\n## 🎯 Планы на завтра" in updated
    assert "Старый текст дня" in updated
