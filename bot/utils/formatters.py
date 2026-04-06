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


def render_task_markdown(
    title: str,
    project_name: str,
    priority: str,
    description: str,
    deadline_iso: str | None,
    estimated_time: float | None,
    created_at: str,
    criteria_items: list[str],
    subtask_items: list[str],
    cursor_prompt: str = "",
    notes: str = "",
    task_type: str = "task",
) -> str:
    """Формирует markdown для задачи в формате Obsidian-шаблона."""
    deadline_line = deadline_iso or ""
    estimated_line = "" if estimated_time is None else str(estimated_time)
    criteria = "\n".join([f"- [ ] {item}" for item in criteria_items]) if criteria_items else "- [ ] Определить критерии"
    subtasks = "\n".join([f"- [ ] {item}" for item in subtask_items]) if subtask_items else "- [ ] Разбить задачу на шаги"

    return (
        "---\n"
        f"title: {title}\n"
        f"project: {project_name}\n"
        "status: 🔴 Новая\n"
        f"priority: {priority}\n"
        f"type: {task_type}\n"
        f"deadline: {deadline_line}\n"
        f"estimated_time: {estimated_line}\n"
        f"created: {created_at}\n"
        "tags: [задача]\n"
        "google_calendar_id: \n"
        "---\n\n"
        "## 📋 Описание\n"
        f"{description}\n\n"
        "## 🎯 Критерии готовности\n"
        f"{criteria}\n\n"
        "## 📝 Подзадачи\n"
        f"{subtasks}\n\n"
        "## 🤖 Cursor AI Промт\n"
        f"{cursor_prompt}\n\n"
        "## 📎 Заметки\n"
        f"{notes}\n"
    )


def render_diary_markdown(
    date_iso: str,
    mood: str,
    day_text: str,
    done_text: str,
    ideas_text: str,
    tomorrow_text: str,
) -> str:
    """Формирует markdown-шаблон дневника за день."""
    return (
        "---\n"
        f"date: {date_iso}\n"
        f"mood: {mood}\n"
        "tags: [дневник]\n"
        "---\n\n"
        "## 🌅 Как прошёл день\n"
        f"{day_text}\n\n"
        "## ✅ Что сделал\n"
        f"{done_text}\n\n"
        "## 💭 Мысли и идеи\n"
        f"{ideas_text}\n\n"
        "## 🎯 Планы на завтра\n"
        f"{tomorrow_text}\n"
    )


def render_diary_append_block(
    mood: str,
    day_text: str,
    done_text: str,
    ideas_text: str,
    tomorrow_text: str,
) -> str:
    """Формирует блок дополнения к существующей записи дневника."""
    return (
        "## ➕ Дополнение\n"
        f"Настроение: {mood}\n\n"
        "### 🌅 Как прошёл день\n"
        f"{day_text}\n\n"
        "### ✅ Что сделал\n"
        f"{done_text}\n\n"
        "### 💭 Мысли и идеи\n"
        f"{ideas_text}\n\n"
        "### 🎯 Планы на завтра\n"
        f"{tomorrow_text}\n"
    )
