"""Pydantic-схемы API."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class AuthInitRequest(BaseModel):
    init_data: str


class AuthInitResponse(BaseModel):
    ok: bool
    user_id: int
    username: str | None = None
    first_name: str | None = None


class ProjectCreateRequest(BaseModel):
    name: str
    description: str = ""
    stack: str = ""
    repo_url: str | None = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    status: str
    stack: str
    repo_url: str | None
    obsidian_path: str
    created_at: datetime


class ProjectStatusUpdateRequest(BaseModel):
    status: str


class TaskCreateRequest(BaseModel):
    project_id: int | None = None
    description: str
    priority: str = "⚡ Средний"
    deadline: date | None = None
    estimated_time: float | None = None
    add_to_calendar: bool = False
    calendar_start: str | None = None
    calendar_end: str | None = None


class TaskResponse(BaseModel):
    id: int
    project_id: int | None
    title: str
    completed: bool
    priority: str
    deadline: date | None
    estimated_time: float | None
    obsidian_path: str
    created_at: datetime


class TaskStatusUpdateRequest(BaseModel):
    completed: bool


class NoteCreateRequest(BaseModel):
    content: str
    note_type: str = "inbox"


class NoteResponse(BaseModel):
    id: int
    title: str
    type: str
    content: str
    tags: str
    obsidian_path: str
    created_at: datetime


class ResourceCreateRequest(BaseModel):
    url: str


class ResourceResponse(BaseModel):
    id: int
    title: str
    url: str
    type: str
    tags: str
    obsidian_path: str
    created_at: datetime


class DiaryTodayPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mood: str = "😐"
    day_text: str = Field(default="", alias="day")
    done_text: str = Field(default="", alias="done")
    ideas_text: str = Field(default="", alias="ideas")
    tomorrow_text: str = Field(default="", alias="tomorrow")


class DiaryTodayResponse(BaseModel):
    date: date
    exists: bool
    obsidian_path: str | None = None
    content: str | None = None


class SettingsPatchRequest(BaseModel):
    timezone: str | None = None
    log_level: str | None = None
    diary_reminder_enabled: bool | None = None
    morning_digest_enabled: bool | None = None


class RuntimeSettingsResponse(BaseModel):
    timezone: str
    diary_reminder_enabled: bool
    morning_digest_enabled: bool
    log_level: str


class SyncResponse(BaseModel):
    ok: bool
    error: str | None = None


class DashboardResponse(BaseModel):
    text: str
