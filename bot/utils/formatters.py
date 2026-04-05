"""Форматтеры markdown и вспомогательных текстов для Obsidian."""

from __future__ import annotations

from datetime import datetime


def now_human() -> str:
    """Человекочитаемая дата и время для шаблонов."""
    return datetime.now().strftime("%Y-%m-%d %H:%M")

