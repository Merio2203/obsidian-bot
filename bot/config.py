"""Конфигурация приложения с загрузкой из .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

VAULT_FOLDERS: dict[str, str] = {
    "projects": "Проекты",
    "diary": "Дневник",
    "resources": "Библиотека",
    "inbox": "Входящие",
}

PROJECT_SUBFOLDERS: tuple[str, str] = ("Задачи", "Библиотека")


@dataclass(frozen=True)
class Settings:
    """Типизированные настройки приложения."""

    telegram_bot_token: str
    telegram_owner_id: int
    routerai_api_key: str
    routerai_base_url: str
    routerai_model: str
    google_client_id: str
    google_client_secret: str
    google_calendar_ids: list[str]
    google_token_file: Path
    vault_path: Path
    dropbox_vault_path: str
    timezone: str
    database_url: str
    log_file: Path
    ai_max_retries: int
    ai_retry_delay_seconds: int


class ConfigError(ValueError):
    """Ошибка валидации конфигурации."""


def _get_required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Отсутствует обязательная переменная окружения: {name}")
    return value


def _parse_owner_id(raw: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError("TELEGRAM_OWNER_ID должен быть целым числом") from exc


def load_settings() -> Settings:
    """Загружает и валидирует настройки из переменных окружения."""
    load_dotenv()

    telegram_bot_token = _get_required("TELEGRAM_BOT_TOKEN")
    telegram_owner_id = _parse_owner_id(_get_required("TELEGRAM_OWNER_ID"))
    routerai_api_key = _get_required("ROUTERAI_API_KEY")
    vault_path = Path(_get_required("VAULT_PATH"))
    dropbox_vault_path = _get_required("DROPBOX_VAULT_PATH")
    timezone = _get_required("TIMEZONE")

    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:////app/data/bot.db").strip()
    if not database_url:
        raise ConfigError("DATABASE_URL не может быть пустым")

    log_file = Path(os.getenv("LOG_FILE", "/app/data/bot.log").strip())

    ai_max_retries = int(os.getenv("AI_MAX_RETRIES", "2").strip())
    ai_retry_delay_seconds = int(os.getenv("AI_RETRY_DELAY_SECONDS", "2").strip())
    if ai_max_retries < 0:
        raise ConfigError("AI_MAX_RETRIES не может быть меньше 0")
    if ai_retry_delay_seconds < 1:
        raise ConfigError("AI_RETRY_DELAY_SECONDS должен быть >= 1")

    google_calendar_ids_raw = os.getenv("GOOGLE_CALENDAR_IDS", "").strip()
    google_calendar_ids = [
        item.strip() for item in google_calendar_ids_raw.split(",") if item.strip()
    ]

    return Settings(
        telegram_bot_token=telegram_bot_token,
        telegram_owner_id=telegram_owner_id,
        routerai_api_key=routerai_api_key,
        routerai_base_url="https://routerai.ru/api/v1",
        routerai_model="anthropic/claude-sonnet-4.6",
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
        google_calendar_ids=google_calendar_ids,
        google_token_file=Path(os.getenv("GOOGLE_TOKEN_FILE", "/app/data/google_token.json").strip()),
        vault_path=vault_path,
        dropbox_vault_path=dropbox_vault_path,
        timezone=timezone,
        database_url=database_url,
        log_file=log_file,
        ai_max_retries=ai_max_retries,
        ai_retry_delay_seconds=ai_retry_delay_seconds,
    )


settings = load_settings()
