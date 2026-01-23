from __future__ import annotations

"""
Google Calendar tools for marlo-inbox agent.

This file will be implemented by Agent 3.
See AGENT_3_PROMPT.md for implementation details.
"""

from langchain_core.tools import StructuredTool
from pydantic import BaseModel


# Placeholder schemas - Agent 3 will implement properly
class GetScheduleInput(BaseModel):
    date: str
    days: int = 1


class CheckAvailabilityInput(BaseModel):
    start_time: str
    end_time: str


class FindFreeSlotsInput(BaseModel):
    date: str
    duration_minutes: int = 30


class CreateEventInput(BaseModel):
    title: str
    start_time: str
    end_time: str
    attendees: list[str] | None = None
    description: str | None = None


class DeleteEventInput(BaseModel):
    event_id: str


# Placeholder implementations - Agent 3 will implement properly
async def _get_schedule(date: str, days: int = 1):
    raise NotImplementedError("To be implemented by Agent 3")


async def _check_availability(start_time: str, end_time: str):
    raise NotImplementedError("To be implemented by Agent 3")


async def _find_free_slots(date: str, duration_minutes: int = 30):
    raise NotImplementedError("To be implemented by Agent 3")


async def _create_event(
    title: str,
    start_time: str,
    end_time: str,
    attendees: list[str] | None = None,
    description: str | None = None,
):
    raise NotImplementedError("To be implemented by Agent 3")


async def _delete_event(event_id: str):
    raise NotImplementedError("To be implemented by Agent 3")


# Tool definitions
get_schedule = StructuredTool(
    name="get_schedule",
    description="Get calendar events for a specific date or date range. Date format: YYYY-MM-DD",
    args_schema=GetScheduleInput,
    coroutine=_get_schedule,
)

check_availability = StructuredTool(
    name="check_availability",
    description="Check if a specific time slot is free or has conflicts. Time format: ISO 8601 (YYYY-MM-DDTHH:MM:SS)",
    args_schema=CheckAvailabilityInput,
    coroutine=_check_availability,
)

find_free_slots = StructuredTool(
    name="find_free_slots",
    description="Find available time slots on a given date for a meeting of specified duration",
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
