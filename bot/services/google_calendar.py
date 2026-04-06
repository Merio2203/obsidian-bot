"""Сервис интеграции с Google Calendar API."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from bot.config import settings

SCOPES = ["https://www.googleapis.com/auth/calendar"]


@dataclass(frozen=True)
class CalendarEvent:
    """Нормализованная модель события календаря."""

    event_id: str
    title: str
    start_label: str
    end_label: str


class GoogleCalendarService:
    """Работа с Google Calendar, если токен уже настроен."""

    def __init__(self, timezone_name: str) -> None:
        self.timezone_name = timezone_name

    @staticmethod
    def _pick_calendar_id() -> str:
        if settings.google_calendar_ids:
            return settings.google_calendar_ids[0]
        return "primary"

    @staticmethod
    def _load_credentials() -> Credentials | None:
        token_file: Path = settings.google_token_file
        if not token_file.exists():
            return None

        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_file.write_text(creds.to_json(), encoding="utf-8")
        if not creds or not creds.valid:
            return None
        return creds

    @staticmethod
    def _format_event_time(item: dict[str, Any], field: str) -> str:
        payload = item.get(field) or {}
        dt = payload.get("dateTime")
        d = payload.get("date")
        if dt:
            parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            return parsed.strftime("%H:%M")
        if d:
            return f"{d} (all-day)"
        return "?"

    async def create_event_for_task(
        self,
        title: str,
        description: str,
        due_date: date,
    ) -> str | None:
        """Создает событие на дату дедлайна и возвращает event_id."""
        creds = await asyncio.to_thread(self._load_credentials)
        if not creds:
            return None

        calendar_id = self._pick_calendar_id()
        event_body = {
            "summary": title,
            "description": description,
            "start": {"date": due_date.isoformat(), "timeZone": self.timezone_name},
            "end": {"date": (due_date + timedelta(days=1)).isoformat(), "timeZone": self.timezone_name},
        }

        def _insert() -> str | None:
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
            return event.get("id")

        return await asyncio.to_thread(_insert)

    async def list_events_for_date(self, target_date: date) -> list[CalendarEvent]:
        """Возвращает события за выбранный день."""
        creds = await asyncio.to_thread(self._load_credentials)
        if not creds:
            return []

        calendar_id = self._pick_calendar_id()
        time_min = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0).isoformat() + "Z"
        next_day = target_date + timedelta(days=1)
        time_max = datetime(next_day.year, next_day.month, next_day.day, 0, 0, 0).isoformat() + "Z"

        def _list() -> list[CalendarEvent]:
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            data = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = []
            for item in data.get("items", []):
                events.append(
                    CalendarEvent(
                        event_id=item.get("id", ""),
                        title=item.get("summary", "Без названия"),
                        start_label=self._format_event_time(item, "start"),
                        end_label=self._format_event_time(item, "end"),
                    )
                )
            return events

        return await asyncio.to_thread(_list)
