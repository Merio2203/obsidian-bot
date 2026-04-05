from __future__ import annotations

from pathlib import Path

import pytest

from bot.services.obsidian_service import ObsidianService


@pytest.mark.asyncio
async def test_write_and_read_markdown(tmp_path: Path) -> None:
    service = ObsidianService(vault_path=tmp_path)

    async def fake_sync() -> tuple[bool, str | None]:
        return True, None

    service.sync_to_dropbox = fake_sync  # type: ignore[method-assign]

    await service.ensure_dirs()
    result = await service.write_markdown("📥 Входящие/test-note.md", "# test")
    content = await service.read_markdown("📥 Входящие/test-note.md")

    assert result.synced is True
    assert content == "# test"


def test_sanitize_filename() -> None:
    assert ObsidianService.sanitize_filename("  Тест: идея / 2026  ") == "тест-идея-2026"
