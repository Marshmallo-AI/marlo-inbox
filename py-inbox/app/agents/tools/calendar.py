from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import marlo
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.core.google_tools import get_access_token_from_config, GoogleAuthError
from app.services.calendar import CalendarService

logger = logging.getLogger(__name__)


def _get_calendar_service(config: RunnableConfig) -> CalendarService:
    """Get Calendar service - must be called within asyncio.to_thread."""
    access_token = get_access_token_from_config(config)
    if not access_token:
        raise GoogleAuthError("Not authenticated. Please log in first.")
    return CalendarService(access_token)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_rfc3339(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _ensure_rfc3339(value: str) -> str:
    if "T" not in value:
        return value
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat().replace("+00:00", "Z")


def _format_datetime(value: str) -> str:
    if "T" not in value:
        return value
    parsed = _parse_rfc3339(value)
    return parsed.isoformat().replace("+00:00", "Z")


def _format_event(event: dict[str, Any]) -> str:
    summary = event.get("summary", "(No title)")
    start = event.get("start", {})
    end = event.get("end", {})
    start_value = start.get("dateTime") or start.get("date") or ""
    end_value = end.get("dateTime") or end.get("date") or ""
    location = event.get("location")
    attendees = event.get("attendees", [])
    attendee_emails = [attendee.get("email") for attendee in attendees if attendee]
    event_id = event.get("id")

    parts = []
    if start_value and end_value and "dateTime" in start:
        parts.append(f"{_format_datetime(start_value)} to {_format_datetime(end_value)}")
    elif start_value:
        parts.append(f"All day on {start_value}")
    if summary:
        parts.append(summary)
    if attendee_emails:
        parts.append(f"attendees: {', '.join(attendee_emails)}")
    if location:
        parts.append(f"location: {location}")
    if event_id:
        parts.append(f"id: {event_id}")
    return " - ".join(parts)


def _build_event_time(value: str) -> dict[str, str]:
    if "T" not in value:
        return {"date": value}
    return {"dateTime": _ensure_rfc3339(value)}


def _get_schedule_sync(config: RunnableConfig, time_min: str, time_max: str) -> list[dict[str, Any]]:
    """Synchronous wrapper for get_schedule."""
    service = _get_calendar_service(config)
    return service.list_events(time_min=time_min, time_max=time_max)


def _check_availability_sync(config: RunnableConfig, time_min: str, time_max: str) -> dict[str, Any]:
    """Synchronous wrapper for check_availability."""
    service = _get_calendar_service(config)
    return service.get_freebusy(time_min=time_min, time_max=time_max)


def _create_event_sync(config: RunnableConfig, event: dict[str, Any], send_updates: str) -> dict[str, Any]:
    """Synchronous wrapper for create_event."""
    service = _get_calendar_service(config)
    return service.create_event(event=event, send_updates=send_updates)


def _delete_event_sync(config: RunnableConfig, event_id: str) -> None:
    """Synchronous wrapper for delete_event."""
    service = _get_calendar_service(config)
    service.delete_event(event_id=event_id)


@tool
@marlo.track_tool
async def get_schedule(date: str, days: int = 1, *, config: RunnableConfig) -> str:
    """Get calendar events for a specific date or date range. Date format: YYYY-MM-DD"""
    start_date = _parse_date(date)
    span = max(days, 1)
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(days=span)
    time_min = start_dt.isoformat().replace("+00:00", "Z")
    time_max = end_dt.isoformat().replace("+00:00", "Z")
    events = await asyncio.to_thread(_get_schedule_sync, config, time_min, time_max)
    if not events:
        return f"No events found from {start_date} for {span} day(s)."
    header = f"Schedule from {start_date} for {span} day(s):"
    formatted = "\n".join(_format_event(event) for event in events)
    return f"{header}\n{formatted}"


@tool
@marlo.track_tool
async def check_availability(start_time: str, end_time: str, *, config: RunnableConfig) -> str:
    """Check if a specific time slot is free or has conflicts. Time format: ISO 8601 (YYYY-MM-DDTHH:MM:SS)"""
    time_min = _ensure_rfc3339(start_time)
    time_max = _ensure_rfc3339(end_time)
    freebusy = await asyncio.to_thread(_check_availability_sync, config, time_min, time_max)
    busy_times = freebusy.get("calendars", {}).get("primary", {}).get("busy", [])
    if not busy_times:
        return f"Free from {time_min} to {time_max}."
    conflicts = ", ".join(
        f"{_format_datetime(item['start'])} to {_format_datetime(item['end'])}"
        for item in busy_times
    )
    return f"Not available. Conflicts: {conflicts}."


@tool
@marlo.track_tool
async def find_free_slots(date: str, duration_minutes: int = 30, *, config: RunnableConfig) -> str:
    """Find available time slots on a given date for a meeting of specified duration."""
    target_date = _parse_date(date)
    working_start = time(hour=9, minute=0)
    working_end = time(hour=18, minute=0)
    start_dt = datetime.combine(target_date, working_start, tzinfo=timezone.utc)
    end_dt = datetime.combine(target_date, working_end, tzinfo=timezone.utc)
    time_min = start_dt.isoformat().replace("+00:00", "Z")
    time_max = end_dt.isoformat().replace("+00:00", "Z")
    freebusy = await asyncio.to_thread(_check_availability_sync, config, time_min, time_max)
    busy_times = freebusy.get("calendars", {}).get("primary", {}).get("busy", [])
    busy_ranges = [
        (
            _parse_rfc3339(item["start"]),
            _parse_rfc3339(item["end"]),
        )
        for item in busy_times
    ]
    busy_ranges.sort(key=lambda item: item[0])

    free_slots: list[tuple[datetime, datetime]] = []
    cursor = start_dt
    duration = timedelta(minutes=max(duration_minutes, 1))
    for busy_start, busy_end in busy_ranges:
        if busy_start > cursor and busy_start - cursor >= duration:
            free_slots.append((cursor, busy_start))
        if busy_end > cursor:
            cursor = busy_end
    if end_dt > cursor and end_dt - cursor >= duration:
        free_slots.append((cursor, end_dt))

    if not free_slots:
        return f"No free slots on {date} for {duration_minutes} minutes."
    slots = "\n".join(
        f"{slot_start.isoformat().replace('+00:00', 'Z')} to {slot_end.isoformat().replace('+00:00', 'Z')}"
        for slot_start, slot_end in free_slots
    )
    return f"Free slots on {date} for {duration_minutes} minutes:\n{slots}"


@tool
@marlo.track_tool
async def create_event(
    title: str,
    start_time: str,
    end_time: str,
    attendees: list[str] | None = None,
    description: str | None = None,
    location: str | None = None,
    *,
    config: RunnableConfig,
) -> str:
    """Create a new calendar event. Optionally invite attendees by email."""
    event = {
        "summary": title,
        "start": _build_event_time(start_time),
        "end": _build_event_time(end_time),
    }
    if attendees:
        event["attendees"] = [{"email": email} for email in attendees]
    if description:
        event["description"] = description
    if location:
        event["location"] = location

    send_updates = "all" if attendees else "none"
    created = await asyncio.to_thread(_create_event_sync, config, event, send_updates)
    event_id = created.get("id", "")
    result = (
        "Event created: "
        f"{title} ({_format_datetime(start_time)} to {_format_datetime(end_time)})"
    )
    if attendees:
        result = f"{result} with attendees: {', '.join(attendees)}"
    if event_id:
        result = f"{result}. Event ID: {event_id}."
    return result


@tool
@marlo.track_tool
async def delete_event(event_id: str, *, config: RunnableConfig) -> str:
    """Delete or cancel a calendar event by ID."""
    await asyncio.to_thread(_delete_event_sync, config, event_id)
    return f"Deleted event {event_id}."
