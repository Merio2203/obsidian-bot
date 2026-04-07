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
    result = await service.write_markdown("Входящие/test-note.md", "# test")
    content = await service.read_markdown("Входящие/test-note.md")

    assert result.synced is True
    assert content == "# test"


@pytest.mark.asyncio
async def test_get_existing_links(tmp_path: Path) -> None:
    service = ObsidianService(vault_path=tmp_path)
    await service.ensure_dirs()
    (tmp_path / "Проекты" / "Проект A").mkdir(parents=True, exist_ok=True)
    (tmp_path / "Проекты" / "Проект A" / "Проект Проект A.md").write_text("ok", encoding="utf-8")
    (tmp_path / "Входящие" / "заметка.md").write_text("ok", encoding="utf-8")

    links = await service.get_existing_links("all")
    assert "Проект Проект A" in links
    assert "заметка" in links

    project_links = await service.get_existing_links("project")
    assert "Проект Проект A" in project_links
    assert "заметка" not in project_links


def test_sanitize_filename() -> None:
    assert ObsidianService.sanitize_filename("  🚀 Тест: идея / 2026  ") == "Тест идея 2026"
    assert ObsidianService.slugify_filename("  🚀 Тест: идея / 2026  ") == "тест-идея-2026"
