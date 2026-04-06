from __future__ import annotations

from bot.services.google_calendar import GoogleCalendarService


def test_format_event_time_datetime() -> None:
    payload = {"start": {"dateTime": "2026-04-07T10:30:00+03:00"}}
    value = GoogleCalendarService._format_event_time(payload, "start")
    assert value == "10:30"


def test_format_event_time_allday() -> None:
    payload = {"start": {"date": "2026-04-07"}}
    value = GoogleCalendarService._format_event_time(payload, "start")
    assert value == "2026-04-07 (all-day)"
