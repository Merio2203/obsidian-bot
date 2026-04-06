"""Форматтеры markdown и вспомогательных текстов для Obsidian."""

from __future__ import annotations

from datetime import datetime, timezone


def now_human() -> str:
    """Человекочитаемая дата и время для шаблонов."""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def today_iso() -> str:
    """Текущая дата в ISO-формате."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def render_project_overview_markdown(
    title: str,
    description: str,
    stack_items: list[str],
    repo_url: str | None,
) -> str:
    """Формирует markdown-файл проекта по шаблону Obsidian."""
    stack_yaml = ", ".join(stack_items) if stack_items else ""
    stack_text = ", ".join(stack_items) if stack_items else "Не указан"
    repo_line = repo_url or "Не указан"
    created = today_iso()

    return (
        "---\n"
        f"title: {title}\n"
        "status: 🟡 Активный\n"
        f"stack: [{stack_yaml}]\n"
        f"repository: {repo_line}\n"
        f"created: {created}\n"
        "tags: [проект, it]\n"
        "---\n\n"
        "## 📖 Описание\n"
        f"{description}\n\n"
        "## 🛠 Стек технологий\n"
        f"{stack_text}\n\n"
        "## 🔗 Ссылки\n"
        f"- Репозиторий: {repo_line}\n\n"
        "## 📊 Прогресс\n"
        "- Проект создан\n"
    )
