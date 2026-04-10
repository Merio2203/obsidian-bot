"""Маршруты HTTP API для Telegram Mini App."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from bot.config import PROJECT_SUBFOLDERS, VAULT_FOLDERS, settings
from bot.database import SessionLocal
from bot.database.crud import (
    create_diary_entry,
    create_note,
    create_project,
    create_resource,
    create_task,
    get_diary_entry_by_date,
    get_project_by_id,
    get_project_by_name,
    get_projects,
    get_task_by_id,
    get_tasks,
    get_tasks_by_completed,
    update_project_status,
    update_task_completed,
)
from bot.database.models import Note, Resource
from bot.handlers.today import build_today_dashboard_text
from bot.services.ai_service import AIService
from bot.services.google_calendar import GoogleCalendarService
from bot.services.obsidian_service import ObsidianService, sync_db_with_vault
from bot.services.parser_service import ParserService
from bot.services.settings_service import SettingsPersistenceError, SettingsService
from bot.utils.formatters import (
    render_diary_markdown,
    render_note_markdown,
    render_project_overview_markdown,
    render_resource_markdown,
    render_task_markdown,
)

from .deps import get_current_user
from .schemas import (
    AuthInitRequest,
    AuthInitResponse,
    DashboardResponse,
    DiaryTodayPayload,
    DiaryTodayResponse,
    NoteCreateRequest,
    NoteResponse,
    ProjectCreateRequest,
    ProjectResponse,
    ProjectStatusUpdateRequest,
    ResourceCreateRequest,
    ResourceResponse,
    RuntimeSettingsResponse,
    SettingsPatchRequest,
    SyncResponse,
    TaskCreateRequest,
    TaskResponse,
    TaskStatusUpdateRequest,
)
from .security import TelegramAuthError, validate_telegram_init_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["miniapp"])

PROJECT_ALLOWED_STATUSES = {"🟡 Активный", "⏸ На паузе", "🟢 Завершён", "🗄 Архив"}
TASK_ALLOWED_PRIORITIES = {"🔥 Высокий", "⚡ Средний", "🌿 Низкий"}


def _normalize_tags(raw: str | list[str] | None, limit: int = 8) -> list[str]:
    if raw is None:
        return []
    src = raw.split(",") if isinstance(raw, str) else [str(x) for x in raw]
    out: list[str] = []
    for item in src:
        token = item.strip().lower().replace(" ", "-")
        if token.startswith("#"):
            token = token[1:]
        if token and token not in out:
            out.append(token)
    return out[:limit]


def _extract_key_points(summary_text: str) -> list[str]:
    points = [line.lstrip("- ").strip() for line in summary_text.splitlines() if line.strip().startswith("-")]
    if points:
        return points[:6]
    return [chunk.strip() for chunk in summary_text.split(".") if chunk.strip()][:4]


def _extract_title(text: str) -> str:
    line = text.strip().splitlines()[0] if text.strip() else "Новая заметка"
    short = line[:60].strip()
    return short or "Новая заметка"


def _parse_hhmm(raw: str | None, default: time) -> time:
    if not raw:
        return default
    try:
        return datetime.strptime(raw, "%H:%M").time()
    except ValueError:
        return default


async def _today_local_date() -> datetime.date:
    runtime = await SettingsService(SessionLocal).get_runtime_settings()
    tz = ZoneInfo(runtime.timezone)
    return datetime.now(tz).date()


@router.get("/health")
async def api_health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/auth/telegram/init", response_model=AuthInitResponse)
async def auth_telegram_init(payload: AuthInitRequest) -> AuthInitResponse:
    try:
        user = validate_telegram_init_data(payload.init_data, bot_token=settings.telegram_bot_token)
    except TelegramAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    if user.id != settings.telegram_owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner-only access")
    return AuthInitResponse(ok=True, user_id=user.id, username=user.username, first_name=user.first_name)


@router.get("/today/dashboard", response_model=DashboardResponse)
async def get_today_dashboard(_user=Depends(get_current_user)) -> DashboardResponse:
    return DashboardResponse(text=await build_today_dashboard_text())


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(_user=Depends(get_current_user)) -> list[ProjectResponse]:
    async with SessionLocal() as session:
        rows = await get_projects(session)
    return [ProjectResponse.model_validate(item, from_attributes=True) for item in rows]


@router.post("/projects", response_model=ProjectResponse)
async def create_project_endpoint(payload: ProjectCreateRequest, _user=Depends(get_current_user)) -> ProjectResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название проекта обязательно")

    async with SessionLocal() as session:
        existing = await get_project_by_name(session, name)
    if existing:
        raise HTTPException(status_code=409, detail="Проект с таким названием уже существует")

    stack_items = [item.strip() for item in payload.stack.split(",") if item.strip()]
    stack_db = ", ".join(stack_items)

    obsidian = ObsidianService()
    project_dir = obsidian.sanitize_filename(name)
    base_dir = obsidian.vault_path / VAULT_FOLDERS["projects"] / project_dir
    for sub in PROJECT_SUBFOLDERS:
        await asyncio.to_thread((base_dir / sub).mkdir, parents=True, exist_ok=True)

    overview_rel = obsidian.get_project_overview_relative(name)
    markdown = render_project_overview_markdown(
        title=f"Проект {name}",
        description=payload.description or "Описание не указано",
        stack_items=stack_items,
        repo_url=payload.repo_url,
    )
    await obsidian.write_markdown(overview_rel, markdown)

    try:
        async with SessionLocal() as session:
            entity = await create_project(
                session=session,
                name=name,
                description=payload.description,
                stack=stack_db,
                repo_url=payload.repo_url,
                obsidian_path=str(overview_rel),
            )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Проект уже существует") from exc

    return ProjectResponse.model_validate(entity, from_attributes=True)


@router.patch("/projects/{project_id}/status", response_model=ProjectResponse)
async def patch_project_status(
    project_id: int,
    payload: ProjectStatusUpdateRequest,
    _user=Depends(get_current_user),
) -> ProjectResponse:
    if payload.status not in PROJECT_ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Некорректный статус")
    async with SessionLocal() as session:
        project = await get_project_by_id(session, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Проект не найден")
        project = await update_project_status(session, project, payload.status)
    return ProjectResponse.model_validate(project, from_attributes=True)


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    project_id: int | None = Query(default=None),
    completed: bool | None = Query(default=None),
    _user=Depends(get_current_user),
) -> list[TaskResponse]:
    async with SessionLocal() as session:
        rows = await (get_tasks_by_completed(session, completed) if completed is not None else get_tasks(session))
    if project_id is not None:
        rows = [x for x in rows if x.project_id == project_id]
    return [TaskResponse.model_validate(item, from_attributes=True) for item in rows]


@router.get("/projects/{project_id}/tasks", response_model=list[TaskResponse])
async def list_project_tasks(
    project_id: int,
    only_open: bool = Query(default=True),
    _user=Depends(get_current_user),
) -> list[TaskResponse]:
    async with SessionLocal() as session:
        rows = await get_tasks(session)
    rows = [item for item in rows if item.project_id == project_id]
    if only_open:
        rows = [item for item in rows if not item.completed]
    return [TaskResponse.model_validate(item, from_attributes=True) for item in rows]


@router.post("/tasks", response_model=TaskResponse)
async def create_task_endpoint(payload: TaskCreateRequest, _user=Depends(get_current_user)) -> TaskResponse:
    if not payload.description.strip():
        raise HTTPException(status_code=400, detail="Описание задачи обязательно")
    if payload.priority not in TASK_ALLOWED_PRIORITIES:
        raise HTTPException(status_code=400, detail="Некорректный приоритет")

    project_id = payload.project_id
    project_name = "Без проекта"
    folder = VAULT_FOLDERS["inbox"]
    if project_id is not None:
        async with SessionLocal() as session:
            project = await get_project_by_id(session, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Проект не найден")
        project_name = project.name
        folder = f"{VAULT_FOLDERS['projects']}/{ObsidianService.sanitize_filename(project.name)}/{PROJECT_SUBFOLDERS[0]}"

    ai = AIService(SessionLocal)
    obsidian = ObsidianService()
    existing_links = await obsidian.get_existing_links("all")
    title = await ai.generate_task_title_from_description(payload.description, project_name)
    title = (title or "").strip()[:120] or "Новая задача"

    tags = ["задача"]
    links = [f"[[Проект {project_name}]]"] if project_name != "Без проекта" else []
    try:
        tags_links = await ai.generate_task_tags_and_links(
            title=title,
            description=payload.description,
            project_name=project_name,
            existing_links=existing_links,
        )
        tags = _normalize_tags(tags_links.get("tags"), limit=5) or tags
    except Exception:
        logger.error("Не удалось сгенерировать AI-теги", exc_info=True)

    google_event_id = None
    if payload.add_to_calendar and payload.deadline:
        try:
            runtime = await SettingsService(SessionLocal).get_runtime_settings()
            calendar = GoogleCalendarService(runtime.timezone)
            start_time = _parse_hhmm(payload.calendar_start, time(10, 0))
            end_time = _parse_hhmm(payload.calendar_end, time(11, 0))
            if end_time <= start_time:
                end_time = (datetime.combine(datetime.now().date(), start_time) + timedelta(hours=1)).time()
            google_event_id = await calendar.create_event_for_task(
                title=title,
                description=payload.description,
                due_date=payload.deadline,
                start_time=start_time,
                end_time=end_time,
            )
        except Exception:
            logger.error("Не удалось создать событие календаря", exc_info=True)

    relative_path = f"{folder}/{obsidian.slugify_filename(title)}.md"
    markdown = render_task_markdown(
        title=title,
        project_name=project_name,
        priority=payload.priority,
        description=payload.description,
        deadline_iso=payload.deadline.isoformat() if payload.deadline else None,
        estimated_time=payload.estimated_time,
        completed=False,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        tags=tags,
        links=links,
        google_calendar_id=google_event_id or "",
    )
    await obsidian.write_markdown(relative_path, markdown)

    async with SessionLocal() as session:
        entity = await create_task(
            session=session,
            project_id=project_id,
            title=title,
            priority=payload.priority,
            task_type="task",
            deadline=payload.deadline,
            estimated_time=payload.estimated_time,
            obsidian_path=relative_path,
            google_event_id=google_event_id,
        )
    return TaskResponse.model_validate(entity, from_attributes=True)


@router.patch("/tasks/{task_id}/status", response_model=TaskResponse)
async def patch_task_status(
    task_id: int,
    payload: TaskStatusUpdateRequest,
    _user=Depends(get_current_user),
) -> TaskResponse:
    async with SessionLocal() as session:
        task = await get_task_by_id(session, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        task = await update_task_completed(session, task, payload.completed)
    return TaskResponse.model_validate(task, from_attributes=True)


@router.get("/notes", response_model=list[NoteResponse])
async def list_notes(_user=Depends(get_current_user)) -> list[NoteResponse]:
    async with SessionLocal() as session:
        result = await session.execute(select(Note).order_by(Note.created_at.desc()))
        notes = list(result.scalars().all())
    return [NoteResponse.model_validate(item, from_attributes=True) for item in notes]


@router.post("/notes", response_model=NoteResponse)
async def create_note_endpoint(payload: NoteCreateRequest, _user=Depends(get_current_user)) -> NoteResponse:
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Текст заметки пуст")

    note_type = payload.note_type.strip().lower() or "inbox"
    title = _extract_title(content)
    ai = AIService(SessionLocal)
    obsidian = ObsidianService()

    try:
        tags = _normalize_tags(await ai.generate_tags(content), limit=5)
    except Exception:
        tags = ["заметка", "входящие" if note_type == "inbox" else "идея"]

    relative_path = f"{VAULT_FOLDERS['inbox']}/{obsidian.slugify_filename(title)}.md"
    markdown = render_note_markdown(title=title, note_type=note_type, tags=tags, content=content, links=[])
    await obsidian.write_markdown(relative_path, markdown)

    async with SessionLocal() as session:
        entity = await create_note(
            session=session,
            title=title,
            note_type=note_type,
            content=content,
            tags=",".join(tags),
            obsidian_path=relative_path,
        )
    return NoteResponse.model_validate(entity, from_attributes=True)


@router.get("/resources", response_model=list[ResourceResponse])
async def list_resources(_user=Depends(get_current_user)) -> list[ResourceResponse]:
    async with SessionLocal() as session:
        result = await session.execute(select(Resource).order_by(Resource.created_at.desc()))
        rows = list(result.scalars().all())
    return [ResourceResponse.model_validate(item, from_attributes=True) for item in rows]


@router.post("/resources", response_model=ResourceResponse)
async def create_resource_endpoint(payload: ResourceCreateRequest, _user=Depends(get_current_user)) -> ResourceResponse:
    url = payload.url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Некорректный URL")

    parser = ParserService()
    ai = AIService(SessionLocal)
    obsidian = ObsidianService()
    try:
        if parser.is_youtube_url(url):
            meta = await parser.parse_youtube(url)
            summary = await ai.summarize_video(meta.title, meta.description, meta.author)
            resource_type = "youtube"
            folder = f"{VAULT_FOLDERS['resources']}/Видео"
            title = meta.title
        elif parser.is_instagram_reel_url(url):
            meta = await parser.parse_instagram_reel(url)
            summary = await ai.summarize_video(meta.title, meta.description, meta.author)
            resource_type = "instagram_reel"
            folder = f"{VAULT_FOLDERS['resources']}/Видео"
            title = meta.title
        else:
            article = await parser.parse_article(url)
            summary = await ai.summarize_article(article.title, article.content)
            resource_type = "article"
            folder = f"{VAULT_FOLDERS['resources']}/Статьи"
            title = article.title
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Не удалось обработать ресурс: {exc}") from exc

    tags = _normalize_tags(await ai.generate_tags(f"{title}\n{summary}"), limit=7)
    markdown = render_resource_markdown(
        title=title,
        url=url,
        resource_type=resource_type,
        tags=tags or ["ресурс", resource_type],
        summary=summary,
        key_points=_extract_key_points(summary),
        links=[],
    )
    relative_path = f"{folder}/{obsidian.slugify_filename(title)}.md"
    await obsidian.write_markdown(relative_path, markdown)

    async with SessionLocal() as session:
        entity = await create_resource(
            session=session,
            title=title,
            url=url,
            resource_type=resource_type,
            tags=",".join(tags),
            obsidian_path=relative_path,
        )
    return ResourceResponse.model_validate(entity, from_attributes=True)


@router.get("/diary/today", response_model=DiaryTodayResponse)
async def get_today_diary(_user=Depends(get_current_user)) -> DiaryTodayResponse:
    today = await _today_local_date()
    async with SessionLocal() as session:
        entry = await get_diary_entry_by_date(session, today)
    if not entry:
        return DiaryTodayResponse(date=today, exists=False)
    content = await ObsidianService().read_markdown(entry.obsidian_path)
    return DiaryTodayResponse(date=today, exists=True, obsidian_path=entry.obsidian_path, content=content)


@router.put("/diary/today", response_model=DiaryTodayResponse)
async def put_today_diary(payload: DiaryTodayPayload, _user=Depends(get_current_user)) -> DiaryTodayResponse:
    today = await _today_local_date()
    date_iso = today.isoformat()
    relative_path = f"{VAULT_FOLDERS['diary']}/{date_iso}.md"
    markdown = render_diary_markdown(
        date_iso=date_iso,
        mood=payload.mood,
        day_text=payload.day_text,
        done_text=payload.done_text,
        ideas_text=payload.ideas_text,
        tomorrow_text=payload.tomorrow_text,
    )
    await ObsidianService().write_markdown(relative_path, markdown)
    async with SessionLocal() as session:
        entry = await get_diary_entry_by_date(session, today)
        if not entry:
            try:
                entry = await create_diary_entry(session, today, relative_path)
            except IntegrityError:
                entry = await get_diary_entry_by_date(session, today)
    return DiaryTodayResponse(date=today, exists=True, obsidian_path=relative_path, content=markdown)


@router.get("/settings", response_model=RuntimeSettingsResponse)
async def get_settings(_user=Depends(get_current_user)) -> RuntimeSettingsResponse:
    cfg = await SettingsService(SessionLocal).get_runtime_settings()
    return RuntimeSettingsResponse(
        timezone=cfg.timezone,
        diary_reminder_enabled=cfg.diary_reminder_enabled,
        morning_digest_enabled=cfg.morning_digest_enabled,
        log_level=cfg.log_level,
    )


@router.patch("/settings", response_model=RuntimeSettingsResponse)
async def patch_settings(payload: SettingsPatchRequest, _user=Depends(get_current_user)) -> RuntimeSettingsResponse:
    svc = SettingsService(SessionLocal)
    try:
        cur = await svc.get_runtime_settings()
        if payload.timezone is not None:
            cur = await svc.set_timezone(payload.timezone)
        if payload.log_level is not None:
            await svc.set_log_level(payload.log_level.upper())
            cur = await svc.get_runtime_settings()
        if payload.diary_reminder_enabled is not None and payload.diary_reminder_enabled != cur.diary_reminder_enabled:
            cur = await svc.toggle_diary_reminder()
        if payload.morning_digest_enabled is not None and payload.morning_digest_enabled != cur.morning_digest_enabled:
            cur = await svc.toggle_morning_digest()
    except SettingsPersistenceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RuntimeSettingsResponse(
        timezone=cur.timezone,
        diary_reminder_enabled=cur.diary_reminder_enabled,
        morning_digest_enabled=cur.morning_digest_enabled,
        log_level=cur.log_level,
    )


@router.post("/settings/sync", response_model=SyncResponse)
async def run_sync(_user=Depends(get_current_user)) -> SyncResponse:
    ok, err = await ObsidianService().sync_bidirectional()
    await sync_db_with_vault()
    return SyncResponse(ok=ok, error=err)
