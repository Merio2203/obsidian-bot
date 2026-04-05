"""Базовые CRUD-операции (будут расширены на следующих этапах)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Project


async def get_projects(session: AsyncSession) -> list[Project]:
    """Возвращает список проектов."""
    result = await session.execute(select(Project).order_by(Project.created_at.desc()))
    return list(result.scalars().all())

