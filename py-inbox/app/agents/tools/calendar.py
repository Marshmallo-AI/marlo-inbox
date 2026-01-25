from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.agents.tools import track_tool_call
from app.core.google_tools import get_calendar_service, require_google_auth

logger = logging.getLogger(__name__)


class GetScheduleInput(BaseModel):
    date: str = Field(..., description="Start date in YYYY-MM-DD format")
    days: int = Field(1, description="Number of days to include")


class CheckAvailabilityInput(BaseModel):
    start_time: str = Field(..., description="Start time in ISO 8601 format")
    end_time: str = Field(..., description="End time in ISO 8601 format")


class FindFreeSlotsInput(BaseModel):
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    duration_minutes: int = Field(30, description="Meeting duration in minutes")


class CreateEventInput(BaseModel):
    title: str = Field(..., description="Event title")
    start_time: str = Field(..., description="Event start time in ISO 8601 format")
    end_time: str = Field(..., description="Event end time in ISO 8601 format")
    attendees: list[str] | None = Field(None, description="Attendee email addresses")
    description: str | None = Field(None, description="Event description")
    location: str | None = Field(None, description="Event location")


class DeleteEventInput(BaseModel):
    event_id: str = Field(..., description="Google Calendar event ID")


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


@require_google_auth
async def _get_schedule(date: str, days: int = 1) -> str:
    tool_input = {"date": date, "days": days}
    try:
        service = get_calendar_service()
        start_date = _parse_date(date)
        span = max(days, 1)
        start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        end_dt = start_dt + timedelta(days=span)
        time_min = start_dt.isoformat().replace("+00:00", "Z")
        time_max = end_dt.isoformat().replace("+00:00", "Z")
        events = service.list_events(time_min=time_min, time_max=time_max)
        if not events:
            result = f"No events found from {start_date} for {span} day(s)."
        else:
            header = f"Schedule from {start_date} for {span} day(s):"
            formatted = "\n".join(_format_event(event) for event in events)
            result = f"{header}\n{formatted}"
        track_tool_call("get_schedule", tool_input, result)
        return result
    except Exception as exc:
        error = str(exc)
        track_tool_call("get_schedule", tool_input, None, error=error)
        raise


@require_google_auth
async def _check_availability(start_time: str, end_time: str) -> str:
    tool_input = {"start_time": start_time, "end_time": end_time}
    try:
        service = get_calendar_service()
        time_min = _ensure_rfc3339(start_time)
        time_max = _ensure_rfc3339(end_time)
        freebusy = service.get_freebusy(time_min=time_min, time_max=time_max)
        busy_times = freebusy.get("calendars", {}).get("primary", {}).get("busy", [])
        if not busy_times:
            result = f"Free from {time_min} to {time_max}."
        else:
            conflicts = ", ".join(
                f"{_format_datetime(item['start'])} to {_format_datetime(item['end'])}"
                for item in busy_times
            )
            result = f"Not available. Conflicts: {conflicts}."
        track_tool_call("check_availability", tool_input, result)
        return result
    except Exception as exc:
        error = str(exc)
        track_tool_call("check_availability", tool_input, None, error=error)
        raise


@require_google_auth
async def _find_free_slots(date: str, duration_minutes: int = 30) -> str:
    tool_input = {"date": date, "duration_minutes": duration_minutes}
    try:
        service = get_calendar_service()
        target_date = _parse_date(date)
        working_start = time(hour=9, minute=0)
        working_end = time(hour=18, minute=0)
        start_dt = datetime.combine(target_date, working_start, tzinfo=timezone.utc)
        end_dt = datetime.combine(target_date, working_end, tzinfo=timezone.utc)
        time_min = start_dt.isoformat().replace("+00:00", "Z")
        time_max = end_dt.isoformat().replace("+00:00", "Z")
        freebusy = service.get_freebusy(time_min=time_min, time_max=time_max)
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
            result = f"No free slots on {date} for {duration_minutes} minutes."
        else:
            slots = "\n".join(
                f"{slot_start.isoformat().replace('+00:00', 'Z')} to {slot_end.isoformat().replace('+00:00', 'Z')}"
                for slot_start, slot_end in free_slots
            )
            result = (
                f"Free slots on {date} for {duration_minutes} minutes:\n{slots}"
            )
        track_tool_call("find_free_slots", tool_input, result)
        return result
    except Exception as exc:
        error = str(exc)
        track_tool_call("find_free_slots", tool_input, None, error=error)
        raise


@require_google_auth
async def _create_event(
    title: str,
    start_time: str,
    end_time: str,
    attendees: list[str] | None = None,
    description: str | None = None,
    location: str | None = None,
) -> str:
    tool_input = {
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "attendees": attendees,
        "description": description,
        "location": location,
    }
    try:
        service = get_calendar_service()
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

        created = service.create_event(
            event=event,
            send_updates="all" if attendees else "none",
        )
        event_id = created.get("id", "")
        result = (
            "Event created: "
            f"{title} ({_format_datetime(start_time)} to {_format_datetime(end_time)})"
        )
        if attendees:
            result = f"{result} with attendees: {', '.join(attendees)}"
        if event_id:
            result = f"{result}. Event ID: {event_id}."
        track_tool_call("create_event", tool_input, result)
        return result
    except Exception as exc:
        error = str(exc)
        track_tool_call("create_event", tool_input, None, error=error)
        raise


def _build_event_time(value: str) -> dict[str, str]:
    if "T" not in value:
        return {"date": value}
    return {"dateTime": _ensure_rfc3339(value)}


@require_google_auth
async def _delete_event(event_id: str) -> str:
    tool_input = {"event_id": event_id}
    try:
        service = get_calendar_service()
        service.delete_event(event_id=event_id)
        result = f"Deleted event {event_id}."
        track_tool_call("delete_event", tool_input, result)
        return result
    except Exception as exc:
        error = str(exc)
        track_tool_call("delete_event", tool_input, None, error=error)
        raise


get_schedule = StructuredTool(
    name="get_schedule",
    description=(
        "Get calendar events for a specific date or date range. "
        "Date format: YYYY-MM-DD"
    ),
    args_schema=GetScheduleInput,
    coroutine=_get_schedule,
)

check_availability = StructuredTool(
    name="check_availability",
    description=(
        "Check if a specific time slot is free or has conflicts. "
        "Time format: ISO 8601 (YYYY-MM-DDTHH:MM:SS)"
    ),
    args_schema=CheckAvailabilityInput,
    coroutine=_check_availability,
)

find_free_slots = StructuredTool(
    name="find_free_slots",
    description=(
        "Find available time slots on a given date for a meeting of specified "
        "duration"
    ),
    args_schema=FindFreeSlotsInput,
    coroutine=_find_free_slots,
)

create_event = StructuredTool(
    name="create_event",
    description="Create a new calendar event. Optionally invite attendees by email.",
    args_schema=CreateEventInput,
    coroutine=_create_event,
)

delete_event = StructuredTool(
    name="delete_event",
    description="Delete or cancel a calendar event by ID",
    args_schema=DeleteEventInput,
    coroutine=_delete_event,
)
