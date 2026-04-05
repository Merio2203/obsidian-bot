"""Общие фикстуры тестов."""

from __future__ import annotations

import os
from pathlib import Path


def pytest_sessionstart(session) -> None:  # type: ignore[no-untyped-def]
    """Устанавливает обязательные env-переменные до импорта модулей приложения."""
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
    os.environ.setdefault("TELEGRAM_OWNER_ID", "42")
    os.environ.setdefault("ROUTERAI_API_KEY", "test-api-key")
    os.environ.setdefault("VAULT_PATH", str(Path.cwd() / "vault"))
    os.environ.setdefault("DROPBOX_VAULT_PATH", "TestVault")
    os.environ.setdefault("TIMEZONE", "Europe/Moscow")
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("LOG_FILE", str(Path.cwd() / "data" / "test.log"))
