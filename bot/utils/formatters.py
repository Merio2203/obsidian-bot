"""Форматтеры markdown и вспомогательных текстов для Obsidian."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def now_human() -> str:
    """Человекочитаемая дата и время для шаблонов."""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def today_iso() -> str:
    """Текущая дата в ISO-формате."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def format_wikilinks_for_yaml(links: list[str]) -> str:
    """
    Формирует YAML-блок links в корректном формате Obsidian.

    Принимает как имена файлов, так и готовые wikilinks.
    """
    formatted: list[str] = []
    for raw_link in links:
        link = raw_link.strip()
        if not link:
            continue

        if link.startswith("[") and "](" in link and link.endswith(")"):
            label = link[1 : link.index("]")]
            target = link[link.index("](") + 2 : -1]
            target_name = Path(target).stem
            link = f"[[{target_name}|{label}]]" if label and label != target_name else f"[[{target_name}]]"
        else:
            if link.startswith("[[") and link.endswith("]]"):
                inner = link[2:-2].strip()
            else:
                inner = link.strip("[]")
            target_part, sep, alias = inner.partition("|")
            target_name = Path(target_part).name
            if target_name.endswith(".md"):
                target_name = target_name[:-3]
            link = f"[[{target_name}|{alias.strip()}]]" if sep and alias.strip() else f"[[{target_name}]]"

        if link not in formatted:
            formatted.append(link)

    if not formatted:
        return "links: []"
    rows = [f'  - "{item}"' for item in formatted]
    return "links:\n" + "\n".join(rows)


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
    progress: int,
    created_at: str,
    tags: list[str],
    links: list[str],
    notes: str = "",
    task_type: str = "task",
    google_calendar_id: str = "",
) -> str:
    """Формирует markdown для задачи в формате Obsidian-шаблона."""
    deadline_line = deadline_iso or ""
    estimated_line = "" if estimated_time is None else str(estimated_time)
    tags_line = ", ".join(tags)
    links_block = format_wikilinks_for_yaml(links)
    if project_name and project_name != "Без проекта":
        project_value = f'"[[Проект {project_name}]]"'
    else:
        project_value = '"Без проекта"'

    return (
        "---\n"
        f"title: {title}\n"
        f"project: {project_value}\n"
        "status: 🔴 Новая\n"
        f"priority: {priority}\n"
        f"type: {task_type}\n"
        f"deadline: {deadline_line}\n"
        f"estimated_time: {estimated_line}\n"
        f"progress: {max(0, min(100, int(progress)))}\n"
        f"created: {created_at}\n"
        f"tags: [{tags_line}]\n"
        f"{links_block}\n"
        f"google_calendar_id: {google_calendar_id}\n"
        "---\n\n"
        "## 📋 Описание\n"
        f"{description}\n\n"
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
    dt = datetime.strptime(date_iso, "%Y-%m-%d")
    title = f"Дневник за {dt.strftime('%d.%m.%Y')}"
    return (
        "---\n"
        f"title: {title}\n"
        "aliases:\n"
        f'  - "{title}"\n'
        f"date: {date_iso}\n"
        f"mood: {mood}\n"
        "tags: [дневник]\n"
        "---\n\n"
        f"# {title}\n\n"
        "## 🌅 Как прошёл день\n"
        f"{day_text}\n\n"
        "## ✅ Что сделал\n"
        f"{done_text}\n\n"
        "## 💭 Мысли и идеи\n"
        f"{ideas_text}\n\n"
        "## 🎯 Планы на завтра\n"
        f"{tomorrow_text}\n"
    )


def render_note_markdown(
    title: str,
    note_type: str,
    tags: list[str],
    content: str,
    links: list[str] | None = None,
) -> str:
    """Формирует markdown для быстрой заметки/идеи."""
    saved = today_iso()
    tags_line = ", ".join(tags)
    links_block = format_wikilinks_for_yaml(links or [])
    return (
        "---\n"
        f"title: {title}\n"
        f"type: {note_type}\n"
        f"tags: [{tags_line}]\n"
        f"{links_block}\n"
        f"saved: {saved}\n"
        "---\n\n"
        "## 📝 Содержание\n"
        f"{content}\n"
    )


def render_resource_markdown(
    title: str,
    url: str,
    resource_type: str,
    tags: list[str],
    summary: str,
    key_points: list[str],
    links: list[str] | None = None,
) -> str:
    """Формирует markdown для сохраненного ресурса."""
    saved = today_iso()
    tags_line = ", ".join(tags)
    links_block = format_wikilinks_for_yaml(links or [])
    points = "\n".join([f"- {point}" for point in key_points]) if key_points else "- Уточнить ключевые мысли"
    return (
        "---\n"
        f"title: {title}\n"
        f"url: {url}\n"
        f"type: {resource_type}\n"
        f"tags: [{tags_line}]\n"
        f"{links_block}\n"
        f"saved: {saved}\n"
        "---\n\n"
        "## 📝 Резюме\n"
        f"{summary}\n\n"
        "## 🔑 Ключевые мысли\n"
        f"{points}\n"
    )
