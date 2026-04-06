"""CRUD-операции для работы с проектами и другими сущностями."""

from __future__ import annotations

from datetime import date
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DiaryEntry, Note, Project, Resource, Task


async def create_project(
    session: AsyncSession,
    name: str,
    description: str,
    stack: str,
    repo_url: str | None,
    obsidian_path: str,
) -> Project:
    """Создает проект и сохраняет его в БД."""
    project = Project(
        name=name,
        status="🟡 Активный",
        stack=stack,
        repo_url=repo_url,
        obsidian_path=obsidian_path,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def get_projects(session: AsyncSession) -> Sequence[Project]:
    """Возвращает список всех проектов."""
    result = await session.execute(select(Project).order_by(Project.created_at.desc()))
    return list(result.scalars().all())


async def get_project_by_id(session: AsyncSession, project_id: int) -> Project | None:
    """Возвращает проект по ID."""
    result = await session.execute(select(Project).where(Project.id == project_id))
    return result.scalar_one_or_none()


async def get_project_by_name(session: AsyncSession, name: str) -> Project | None:
    """Возвращает проект по имени."""
    result = await session.execute(select(Project).where(Project.name == name))
    return result.scalar_one_or_none()


async def update_project_status(session: AsyncSession, project: Project, status: str) -> Project:
    """Обновляет статус проекта."""
    project.status = status
    await session.commit()
    await session.refresh(project)
    return project


async def create_task(
    session: AsyncSession,
    project_id: int | None,
    title: str,
    priority: str,
    task_type: str,
    deadline,
    estimated_time: float | None,
    obsidian_path: str,
    google_event_id: str | None = None,
) -> Task:
    """Создает задачу и сохраняет в БД."""
    task = Task(
        project_id=project_id,
        title=title,
        status="🔴 Новая",
        priority=priority,
        type=task_type,
        deadline=deadline,
        estimated_time=estimated_time,
        obsidian_path=obsidian_path,
        google_event_id=google_event_id,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def get_tasks(session: AsyncSession) -> Sequence[Task]:
    """Возвращает список задач."""
    result = await session.execute(select(Task).order_by(Task.created_at.desc()))
    return list(result.scalars().all())


async def get_task_by_id(session: AsyncSession, task_id: int) -> Task | None:
    """Возвращает задачу по ID."""
    result = await session.execute(select(Task).where(Task.id == task_id))
    return result.scalar_one_or_none()


async def update_task_status(session: AsyncSession, task: Task, status: str) -> Task:
    """Обновляет статус задачи."""
    task.status = status
    await session.commit()
    await session.refresh(task)
    return task


async def get_diary_entry_by_date(session: AsyncSession, entry_date: date) -> DiaryEntry | None:
    """Возвращает запись дневника по дате."""
    result = await session.execute(select(DiaryEntry).where(DiaryEntry.date == entry_date))
    return result.scalar_one_or_none()


async def create_diary_entry(session: AsyncSession, entry_date: date, obsidian_path: str) -> DiaryEntry:
    """Создает запись дневника в БД."""
    entry = DiaryEntry(date=entry_date, obsidian_path=obsidian_path)
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def create_note(
    session: AsyncSession,
    title: str,
    note_type: str,
    content: str,
    tags: str,
    obsidian_path: str,
) -> Note:
    """Создает быструю заметку (идея/входящие)."""
    note = Note(
        title=title,
        type=note_type,
        content=content,
        tags=tags,
        obsidian_path=obsidian_path,
    )
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


async def create_resource(
    session: AsyncSession,
    title: str,
    url: str,
    resource_type: str,
    tags: str,
    obsidian_path: str,
) -> Resource:
    """Создает ресурс (статья или видео)."""
    resource = Resource(
        title=title,
        url=url,
        type=resource_type,
        tags=tags,
        obsidian_path=obsidian_path,
    )
    session.add(resource)
    await session.commit()
    await session.refresh(resource)
    return resource
