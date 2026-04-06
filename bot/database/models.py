"""SQLAlchemy модели для основных сущностей бота."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Возвращает текущее время в UTC."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Базовый класс декларативных моделей."""


class Project(Base):
    """Проект в Obsidian."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="🟡 Активный")
    stack: Mapped[str] = mapped_column(Text, nullable=False, default="")
    repo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    obsidian_path: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    tasks: Mapped[list["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Task(Base):
    """Задача проекта или личная задача."""

    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_deadline", "deadline"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="🔴 Новая")
    priority: Mapped[str] = mapped_column(String(64), nullable=False, default="⚡ Средний")
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="task")
    deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    estimated_time: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    obsidian_path: Mapped[str] = mapped_column(String(512), nullable=False)
    google_event_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    project: Mapped[Optional[Project]] = relationship(back_populates="tasks")


class Resource(Base):
    """Сохраненный ресурс (статья/видео)."""

    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="")
    obsidian_path: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class DiaryEntry(Base):
    """Запись дневника по дате."""

    __tablename__ = "diary_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    obsidian_path: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AICache(Base):
    """Кэш ответов AI для экономии токенов."""

    __tablename__ = "ai_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


async def init_db(engine: AsyncEngine) -> None:
    """Создает все таблицы в БД (этап 1 без миграций)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


ModelType = Any
JsonDict = dict[str, Any]
