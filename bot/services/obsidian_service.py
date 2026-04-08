"""Сервис файловых операций для Obsidian Vault."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import unicodedata
from datetime import date
from dataclasses import dataclass
from pathlib import Path

from bot.config import PROJECT_SUBFOLDERS, VAULT_FOLDERS, settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WriteResult:
    """Результат записи markdown-файла."""

    path: Path
    synced: bool
    sync_error: str | None = None


class ObsidianService:
    """Единая точка работы с файлами vault + синхронизацией."""

    REQUIRED_DIRS = tuple(VAULT_FOLDERS.values())

    def __init__(self, vault_path: Path | None = None) -> None:
        self.vault_path = vault_path or settings.vault_path

    async def ensure_dirs(self) -> None:
        """Создает стандартные директории vault при старте."""
        for dirname in self.REQUIRED_DIRS:
            directory = self.vault_path / dirname
            await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)

        # Вложенные папки раздела ресурсов.
        await asyncio.to_thread(
            (self.vault_path / VAULT_FOLDERS["resources"] / "Статьи").mkdir,
            parents=True,
            exist_ok=True,
        )
        await asyncio.to_thread(
            (self.vault_path / VAULT_FOLDERS["resources"] / "Видео").mkdir,
            parents=True,
            exist_ok=True,
        )

    async def write_markdown(self, relative_path: str | Path, content: str) -> WriteResult:
        """
        Атомарно записывает markdown в vault и запускает sync.
        Ошибка sync не ломает запись, а возвращается в результате.
        """
        pull_ok, pull_error = await self.sync_from_dropbox()
        if not pull_ok and pull_error:
            logger.warning("Предварительный sync из Dropbox завершился с ошибкой: %s", pull_error)

        target = self.vault_path / Path(relative_path)
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(self._atomic_write, target, content)

        push_ok, push_error = await self.sync_to_dropbox()
        errors = []
        if pull_error:
            errors.append(f"pull: {pull_error}")
        if push_error:
            errors.append(f"push: {push_error}")
        return WriteResult(
            path=target,
            synced=pull_ok and push_ok,
            sync_error="; ".join(errors) if errors else None,
        )

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
        Для проектов исключает "голые" имена папок (например `Sever VPN`),
        чтобы AI выбирал только заметки вида `Проект Sever VPN`.
        """
        folder_map = {
            "project": VAULT_FOLDERS["projects"],
            "projects": VAULT_FOLDERS["projects"],
            "task": VAULT_FOLDERS["projects"],
            "tasks": VAULT_FOLDERS["projects"],
            "diary": VAULT_FOLDERS["diary"],
            "resource": VAULT_FOLDERS["resources"],
            "resources": VAULT_FOLDERS["resources"],
            "inbox": VAULT_FOLDERS["inbox"],
            "note": None,
            "notes": None,
            "all": None,
        }

        folder = folder_map.get(content_type or "all")
        search_path = self.vault_path / folder if folder else self.vault_path

        if not await asyncio.to_thread(search_path.exists):
            return []

        files = await asyncio.to_thread(lambda: list(search_path.rglob("*.md")))
        names = {file_path.stem for file_path in files if file_path.is_file()}

        projects_path = self.vault_path / VAULT_FOLDERS["projects"]
        folder_names: set[str] = set()
        if await asyncio.to_thread(projects_path.exists):
            project_dirs = await asyncio.to_thread(lambda: list(projects_path.iterdir()))
            folder_names = {item.name for item in project_dirs if item.is_dir()}

        filtered = sorted(name for name in names if name not in folder_names)
        return filtered[:1000]

    async def get_projects_from_vault(self) -> list[dict[str, str]]:
        """
        Возвращает список проектов напрямую из файловой системы vault.
        Источник истины для списка проектов — папки внутри `vault/Проекты`.
        """
        projects_path = self.vault_path / VAULT_FOLDERS["projects"]
        if not await asyncio.to_thread(projects_path.exists):
            return []

        def _scan() -> list[dict[str, str]]:
            items: list[dict[str, str]] = []
            for item in sorted(projects_path.iterdir(), key=lambda p: p.name.lower()):
                if not item.is_dir():
                    continue
                overview = item / f"Проект {item.name}.md"
                status = "🟡 Активный"
                if overview.exists():
                    content = overview.read_text(encoding="utf-8")
                    match = re.search(r"^status:\s*(.+)$", content, re.MULTILINE)
                    if match:
                        status = match.group(1).strip()
                items.append({"name": item.name, "path": str(item), "status": status})
            return items

        return await asyncio.to_thread(_scan)

    def get_project_overview_relative(self, project_name: str) -> Path:
        """Возвращает относительный путь обзорного файла проекта."""
        project_dir = self.sanitize_filename(project_name)
        overview_name = self.sanitize_filename(f"Проект {project_name}")
        return Path(VAULT_FOLDERS["projects"]) / project_dir / f"{overview_name}.md"

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """
        Убирает эмодзи и спецсимволы из имени файла/папки.
        Оставляет буквы, цифры, пробел, дефис, точку и скобки.
        """
        cleaned = "".join(
            c
            for c in name
            if unicodedata.category(c) not in ("So", "Cs") and ord(c) < 0x10000
        )
        cleaned = re.sub(r"[\\/:*?\"<>|]", "", cleaned)
        cleaned = re.sub(r"[^\w .()\-А-Яа-яЁё]", " ", cleaned, flags=re.UNICODE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or "untitled"

    @classmethod
    def slugify_filename(cls, name: str, max_length: int = 50) -> str:
        """Готовит короткий slug для имени файла: строчные буквы, цифры, дефисы."""
        sanitized = cls.sanitize_filename(name).lower()
        slug = re.sub(r"\s+", "-", sanitized)
        slug = re.sub(r"[^a-zа-яё0-9\-]", "-", slug)
        slug = re.sub(r"-{2,}", "-", slug).strip("-")
        if len(slug) > max_length:
            slug = slug[:max_length].rstrip("-")
        return slug or "untitled"

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

    async def sync_from_dropbox(self) -> tuple[bool, str | None]:
        """
        Подтягивает изменения из Dropbox в локальный vault.
        Использует copy + --update, чтобы не перезаписывать более новые локальные файлы.
        """
        process = await asyncio.create_subprocess_exec(
            "rclone",
            "copy",
            f"dropbox:{settings.dropbox_vault_path}",
            str(self.vault_path),
            "--update",
            "--create-empty-src-dirs",
            "--quiet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            error_text = stderr.decode("utf-8", errors="ignore").strip() or "unknown error"
            logger.error("Ошибка rclone pull: %s", error_text, exc_info=True)
            return False, error_text
        return True, None

    async def sync_bidirectional(self) -> tuple[bool, str | None]:
        """Двусторонняя синхронизация: сначала pull, затем push."""
        pull_ok, pull_error = await self.sync_from_dropbox()
        push_ok, push_error = await self.sync_to_dropbox()
        errors = []
        if pull_error:
            errors.append(f"pull: {pull_error}")
        if push_error:
            errors.append(f"push: {push_error}")
        return pull_ok and push_ok, "; ".join(errors) if errors else None

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

    @staticmethod
    def parse_frontmatter(markdown: str) -> dict[str, str]:
        """Извлекает плоский YAML frontmatter (ключ: значение) из markdown."""
        text = markdown.lstrip()
        if not text.startswith("---\n"):
            return {}
        end_idx = text.find("\n---", 4)
        if end_idx == -1:
            return {}
        block = text[4:end_idx]
        result: dict[str, str] = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                result[key] = value
        return result

    @staticmethod
    def parse_completed_value(raw: str | None) -> bool:
        """Преобразует строку completed/status в bool."""
        if raw is None:
            return False
        val = raw.strip().lower()
        if val in {"true", "1", "yes", "да"}:
            return True
        if val in {"false", "0", "no", "нет", ""}:
            return False
        # Backward compatibility для старых markdown status-значений.
        if "готов" in val:
            return True
        return False


async def sync_db_with_vault() -> None:
    """
    Синхронизирует SQLite с фактическим состоянием vault.
    - удаляет проекты/задачи, которых больше нет в файлах;
    - добавляет проекты, найденные в vault, но отсутствующие в БД.
    """
    from sqlalchemy import select

    from bot.database import SessionLocal, engine
    from bot.database.models import Project, Task, init_db

    # Гарантируем актуальную схему перед любыми SELECT (в т.ч. для добавленных колонок).
    await init_db(engine)

    service = ObsidianService()
    vault_projects = await service.get_projects_from_vault()
    vault_project_names = {item["name"] for item in vault_projects}
    vault_project_payload = {item["name"]: item for item in vault_projects}

    async with SessionLocal() as session:
        db_projects = list((await session.execute(select(Project))).scalars().all())
        for project in db_projects:
            if project.name not in vault_project_names:
                await session.delete(project)

        db_projects_after_delete = list((await session.execute(select(Project))).scalars().all())
        existing_by_name = {p.name: p for p in db_projects_after_delete}

        for project_name, payload in vault_project_payload.items():
            overview_rel = str(service.get_project_overview_relative(project_name))
            if project_name in existing_by_name:
                existing = existing_by_name[project_name]
                existing.status = payload.get("status", existing.status)
                existing.obsidian_path = overview_rel
            else:
                session.add(
                    Project(
                        name=project_name,
                        status=payload.get("status", "🟡 Активный"),
                        stack="",
                        repo_url=None,
                        obsidian_path=overview_rel,
                    )
                )

        # Нужны id добавленных проектов для привязки задач.
        await session.flush()
        projects_by_name = {p.name: p for p in (await session.execute(select(Project))).scalars().all()}

        # Обновляем/добавляем задачи из markdown-файлов vault.
        discovered_task_paths: set[str] = set()
        all_md_files = await asyncio.to_thread(lambda: list(service.vault_path.rglob("*.md")))
        for abs_file in all_md_files:
            try:
                rel_path = abs_file.relative_to(service.vault_path).as_posix()
            except ValueError:
                continue

            is_project_task = rel_path.startswith(f"{VAULT_FOLDERS['projects']}/") and f"/{PROJECT_SUBFOLDERS[0]}/" in rel_path
            is_inbox = rel_path.startswith(f"{VAULT_FOLDERS['inbox']}/")
            if not (is_project_task or is_inbox):
                continue

            content = await asyncio.to_thread(abs_file.read_text, "utf-8")
            meta = ObsidianService.parse_frontmatter(content)
            task_type = (meta.get("type") or "").strip().lower()
            if task_type and task_type not in {"task", "cursor_prompt"}:
                continue

            discovered_task_paths.add(rel_path)

            raw_title = (meta.get("title") or "").strip()
            title = raw_title or abs_file.stem
            priority = (meta.get("priority") or "⚡ Средний").strip() or "⚡ Средний"
            completed = ObsidianService.parse_completed_value(meta.get("completed"))
            deadline_raw = (meta.get("deadline") or "").strip()
            deadline_value = None
            if deadline_raw:
                try:
                    deadline_value = date.fromisoformat(deadline_raw)
                except ValueError:
                    deadline_value = None
            estimate_raw = (meta.get("estimated_time") or "").strip()
            estimate_value = None
            if estimate_raw:
                try:
                    estimate_value = float(estimate_raw.replace(",", "."))
                except ValueError:
                    estimate_value = None

            google_event_id = (meta.get("google_calendar_id") or "").strip() or None
            normalized_type = task_type or "task"
            status_legacy = "🟢 Готово" if completed else "🕒 В процессе"

            project_id = None
            if is_project_task:
                parts = rel_path.split("/")
                if len(parts) >= 3:
                    project_name = parts[1]
                    project_obj = projects_by_name.get(project_name)
                    if project_obj:
                        project_id = project_obj.id

            existing_task = (
                await session.execute(select(Task).where(Task.obsidian_path == rel_path))
            ).scalar_one_or_none()
            if existing_task:
                existing_task.project_id = project_id
                existing_task.title = title
                existing_task.priority = priority
                existing_task.type = normalized_type
                existing_task.deadline = deadline_value
                existing_task.estimated_time = estimate_value
                existing_task.completed = completed
                existing_task.status = status_legacy
                existing_task.google_event_id = google_event_id
            else:
                session.add(
                    Task(
                        project_id=project_id,
                        title=title,
                        status=status_legacy,
                        completed=completed,
                        priority=priority,
                        type=normalized_type,
                        deadline=deadline_value,
                        estimated_time=estimate_value,
                        obsidian_path=rel_path,
                        google_event_id=google_event_id,
                    )
                )

        # Удаляем задачи из БД, файлов которых больше нет.
        db_tasks = list((await session.execute(select(Task))).scalars().all())
        for task in db_tasks:
            task_path = service.vault_path / task.obsidian_path
            exists = await asyncio.to_thread(task_path.exists)
            if not exists or (discovered_task_paths and task.obsidian_path not in discovered_task_paths):
                await session.delete(task)

        await session.commit()
