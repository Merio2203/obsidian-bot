"""CRUD-операции для работы с проектами и другими сущностями."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Project


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
