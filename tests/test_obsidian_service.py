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


@pytest.mark.asyncio
async def test_get_projects_from_vault(tmp_path: Path) -> None:
    service = ObsidianService(vault_path=tmp_path)
    await service.ensure_dirs()
    project_dir = tmp_path / "Проекты" / "Sever VPN"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "Проект Sever VPN.md").write_text(
        "---\nstatus: 🟢 Завершён\n---\n",
        encoding="utf-8",
    )

    projects = await service.get_projects_from_vault()
    assert projects
    assert projects[0]["name"] == "Sever VPN"
    assert projects[0]["status"] == "🟢 Завершён"


def test_sanitize_filename() -> None:
    assert ObsidianService.sanitize_filename("  🚀 Тест: идея / 2026  ") == "Тест идея 2026"
    assert ObsidianService.slugify_filename("  🚀 Тест: идея / 2026  ") == "тест-идея-2026"
