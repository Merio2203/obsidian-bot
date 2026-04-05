from __future__ import annotations

import importlib
import os

import pytest


def test_load_settings_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc")
    monkeypatch.setenv("TELEGRAM_OWNER_ID", "100")
    monkeypatch.setenv("ROUTERAI_API_KEY", "key")
    monkeypatch.setenv("VAULT_PATH", "/tmp/vault")
    monkeypatch.setenv("DROPBOX_VAULT_PATH", "Vault")
    monkeypatch.setenv("TIMEZONE", "Europe/Moscow")

    config = importlib.import_module("bot.config")
    importlib.reload(config)

    settings = config.load_settings()
    assert settings.telegram_owner_id == 100
    assert settings.routerai_model == "anthropic/claude-sonnet-4.6"


def test_load_settings_missing_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    config = importlib.import_module("bot.config")
    importlib.reload(config)

    with pytest.raises(config.ConfigError):
        config.load_settings()

    os.environ["TELEGRAM_BOT_TOKEN"] = "restore"
