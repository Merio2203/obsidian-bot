"""Сервис файловых операций для Obsidian Vault."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from bot.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WriteResult:
    """Результат записи markdown-файла."""

    path: Path
    synced: bool
    sync_error: str | None = None


class ObsidianService:
    """Единая точка работы с файлами vault + синхронизацией."""

    REQUIRED_DIRS = ("📁 Проекты", "📓 Дневник", "💡 Идеи", "📚 Ресурсы", "📥 Входящие")

    def __init__(self, vault_path: Path | None = None) -> None:
        self.vault_path = vault_path or settings.vault_path

    async def ensure_dirs(self) -> None:
        """Создает стандартные директории vault при старте."""
        for dirname in self.REQUIRED_DIRS:
            directory = self.vault_path / dirname
            await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)

        # Вложенные папки раздела ресурсов.
        await asyncio.to_thread((self.vault_path / "📚 Ресурсы" / "Статьи").mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread((self.vault_path / "📚 Ресурсы" / "Видео").mkdir, parents=True, exist_ok=True)

    async def write_markdown(self, relative_path: str | Path, content: str) -> WriteResult:
        """
        Атомарно записывает markdown в vault и запускает sync.
        Ошибка sync не ломает запись, а возвращается в результате.
        """
        target = self.vault_path / Path(relative_path)
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(self._atomic_write, target, content)

        synced, sync_error = await self.sync_to_dropbox()
        return WriteResult(path=target, synced=synced, sync_error=sync_error)

    async def read_markdown(self, relative_path: str | Path) -> str:
        """Читает markdown из vault."""
        target = self.vault_path / Path(relative_path)
        return await asyncio.to_thread(target.read_text, "utf-8")

    async def update_markdown(self, relative_path: str | Path, append_text: str) -> WriteResult:
        """Дописывает текст в markdown-файл с сохранением атомарности."""
        current = await self.read_markdown(relative_path)
        new_content = f"{current.rstrip()}\n\n{append_text.strip()}\n"
        return await self.write_markdown(relative_path, new_content)

    async def get_existing_links(self, content_type: str | None = None) -> list[str]:
        """
        Возвращает список имён файлов vault без расширения .md.
        Используется как контекст для генерации корректных Obsidian wikilinks.
        """
        folder_map = {
            "project": "📁 Проекты",
            "projects": "📁 Проекты",
            "task": "📁 Проекты",
            "tasks": "📁 Проекты",
            "diary": "📓 Дневник",
            "resource": "📚 Ресурсы",
            "resources": "📚 Ресурсы",
            "idea": "💡 Идеи",
            "inbox": "📥 Входящие",
            "note": None,
            "notes": None,
            "all": None,
        }

        folder = folder_map.get(content_type or "all")
        search_path = self.vault_path / folder if folder else self.vault_path

        if not await asyncio.to_thread(search_path.exists):
            return []

        files = await asyncio.to_thread(lambda: list(search_path.rglob("*.md")))
        names = sorted({file_path.stem for file_path in files if file_path.is_file()})
        return names[:1000]

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Создает безопасное имя файла."""
        sanitized = re.sub(r"[\\/:*?\"<>|]", "", name.strip())
        sanitized = re.sub(r"\s+", "-", sanitized)
        sanitized = re.sub(r"-{2,}", "-", sanitized)
        return sanitized.strip("-").lower() or "untitled"

    async def sync_to_dropbox(self) -> tuple[bool, str | None]:
        """Запускает rclone sync для vault."""
        process = await asyncio.create_subprocess_exec(
            "rclone",
            "sync",
            str(self.vault_path),
            f"dropbox:{settings.dropbox_vault_path}",
            "--quiet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            error_text = stderr.decode("utf-8", errors="ignore").strip() or "unknown error"
            logger.error("Ошибка rclone sync: %s", error_text, exc_info=True)
            return False, error_text
        return True, None

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        """Атомарная запись через временный файл и os.replace."""
        tmp_file: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as fp:
                fp.write(content)
                fp.flush()
                os.fsync(fp.fileno())
                tmp_file = fp.name

            os.replace(tmp_file, path)
        finally:
            if tmp_file and os.path.exists(tmp_file):
                os.unlink(tmp_file)
